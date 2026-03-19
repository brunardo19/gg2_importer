from dataclasses import dataclass

import bpy
import struct
import mathutils
import os
import tempfile
import uuid

def apply_motion_to_armature(armature, motion_data, action_name):
    pose_bones = armature.pose.bones

    if not armature.animation_data:
        armature.animation_data_create()

    if motion_data.track_count != len(pose_bones):
        action = bpy.data.actions.new(name=f"{action_name}-broken")
        return action
    
    action = bpy.data.actions.new(name=action_name)
    armature.animation_data.action = action

    for track_index, track in enumerate(motion_data.tracks):
        target_bone_name = f"bone_{track_index}"
        pose_bone = pose_bones.get(target_bone_name)

        if pose_bone is None:
            continue

        # Set rotation mode once per bone, not every frame
        pose_bone.rotation_mode = "QUATERNION"

        # Pre-calculate inverted relative matrix once per track
        if pose_bone.parent:
            par = pose_bone.parent
            relative_matrix_inv = (par.bone.matrix_local.inverted() @ pose_bone.bone.matrix_local).inverted()
        else:
            relative_matrix_inv = pose_bone.bone.matrix_local.inverted()
            
        rel_inv_quat = relative_matrix_inv.decompose()[1]

        # Prepare flat coordinate lists
        rot_data = {0: [], 1: [], 2: [], 3: []}
        loc_data = {0: [], 1: [], 2: []}
        scl_data = {0: [], 1: [], 2: []}

        for keyframe in track.keyframes:
            if keyframe is None:
                continue
            frame = keyframe.time

            # Collect Rotation
            if keyframe.rotation:
                blender_pose_quat = rel_inv_quat @ keyframe.rotation
                if blender_pose_quat.w < 0:
                    blender_pose_quat.negate()
                
                rot_data[0].extend((frame, blender_pose_quat.w))
                rot_data[1].extend((frame, blender_pose_quat.x))
                rot_data[2].extend((frame, blender_pose_quat.y))
                rot_data[3].extend((frame, blender_pose_quat.z))

            # Collect Translation
            if keyframe.translation:
                blender_pose_vec = relative_matrix_inv @ keyframe.translation
                loc_data[0].extend((frame, blender_pose_vec.x))
                loc_data[1].extend((frame, blender_pose_vec.y))
                loc_data[2].extend((frame, blender_pose_vec.z))

            # Collect Scale
            if keyframe.scale:
                blender_pose_scale = keyframe.scale
                scl_data[0].extend((frame, blender_pose_scale.x))
                scl_data[1].extend((frame, blender_pose_scale.y))
                scl_data[2].extend((frame, blender_pose_scale.z))

        # Helper function to bulk-add fcurves
        def batch_add_fcurves(data_dict, data_path, length):
            if not any(data_dict.values()):
                return
            
            fcurves = [action.fcurves.new(data_path=data_path, index=i) for i in range(length)]
            for i in range(length):
                coords = data_dict[i]
                if coords:
                    num_points = len(coords) // 2
                    fcurves[i].keyframe_points.add(num_points)
                    fcurves[i].keyframe_points.foreach_set('co', coords)
                    fcurves[i].update()

        # Build F-Curves
        base_path = f'pose.bones["{target_bone_name}"]'
        batch_add_fcurves(rot_data, f'{base_path}.rotation_quaternion', 4)
        batch_add_fcurves(loc_data, f'{base_path}.location', 3)
        batch_add_fcurves(scl_data, f'{base_path}.scale', 3)

    action.use_fake_user = True
    return action

def save_and_load_dds(byte_data, filepath):
    if not byte_data:
        return None

    data = bytearray(byte_data)
    if data[0:4] == b"DDS ":
        data[112:124] = b"\x00" * 12  # Zero out volume texture flags
        
    directory, filename = os.path.split(filepath)
    name, ext = os.path.splitext(filename)
    unique_filename = f"{name}_{uuid.uuid4().hex[:8]}{ext}"
    safe_filepath = os.path.join(directory, unique_filename)

    with open(safe_filepath, "wb") as f:
        f.write(data)

    try:
        return bpy.data.images.load(safe_filepath)
    except RuntimeError:
        print(f"Failed to load image at {safe_filepath}.")
        return None

def create_and_assign_material(meshes, material_name, texture_bytes=None, normal_bytes=None, comb_bytes=None, texture_names=None):
    temp_dir = tempfile.gettempdir()
    materials = []

    for i in range(len(meshes)):
        mat = bpy.data.materials.new(name=material_name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links

        for node in nodes:
            nodes.remove(node)

        output_node = nodes.new(type="ShaderNodeOutputMaterial")
        output_node.location = (300, 0)
        bsdf_node = nodes.new(type="ShaderNodeBsdfPrincipled")
        bsdf_node.location = (0, 0)

        links.new(bsdf_node.outputs["BSDF"], output_node.inputs["Surface"])

        print(f"Creating material '{material_name}' for mesh {i} with texture index {meshes[i]['texture_idx']}")
        if texture_bytes[meshes[i]["texture_idx"]]:
            tex_filepath = os.path.join(temp_dir, f"{texture_names[meshes[i]['texture_idx']]}_diffuse.dds")
            print(f"Using texture index {meshes[i]['texture_idx']} for mesh {i}, saving to {tex_filepath}")
            img = save_and_load_dds(texture_bytes[meshes[i]["texture_idx"]], tex_filepath)
            if img:
                tex_node = nodes.new(type="ShaderNodeTexImage")
                tex_node.location = (-300, 0)
                tex_node.image = img
                links.new(tex_node.outputs["Color"], bsdf_node.inputs["Base Color"])
                links.new(tex_node.outputs["Alpha"], bsdf_node.inputs["Alpha"])
    
        if normal_bytes:
            norm_filepath = os.path.join(temp_dir, f"{texture_names[meshes[i]['texture_idx']]}_normal.dds")
            norm_img = save_and_load_dds(normal_bytes, norm_filepath)
            if norm_img:
                norm_img.colorspace_settings.name = "Non-Color"
                norm_tex_node = nodes.new(type="ShaderNodeTexImage")
                norm_tex_node.location = (-600, -300)
                norm_tex_node.image = norm_img

                norm_map_node = nodes.new(type="ShaderNodeNormalMap")
                norm_map_node.location = (-300, -300)

                links.new(norm_tex_node.outputs["Color"], norm_map_node.inputs["Color"])
                links.new(norm_map_node.outputs["Normal"], bsdf_node.inputs["Normal"])

        if comb_bytes:
            comb_filepath = os.path.join(temp_dir, f"{texture_names[meshes[i]['texture_idx']]}_comb.dds")
            comb_img = save_and_load_dds(comb_bytes, comb_filepath)
            if comb_img:
                comb_tex_node = nodes.new(type="ShaderNodeTexImage")
                comb_tex_node.location = (-900, -600)
                comb_tex_node.image = comb_img
                rgb_separator = nodes.new("ShaderNodeSeparateColor")
                rgb_separator.location = (300, -600)
                
                links.new(comb_tex_node.outputs["Color"], rgb_separator.inputs["Color"])
                #links.new(rgb_separator.outputs["Red"], bsdf_node.inputs["IOR"])
                
        materials.append(mat)

    for i, obj in enumerate(meshes):
            obj["mesh"].data.materials.append(materials[i])
    return mat

def _findall(p, s):
    i = s.find(p)
    while i != -1:
        yield i
        i = s.find(p, i + 1)

def _strip_to_triangles(indices):
    faces = []
    for i in range(len(indices) - 2):
        if indices[i] == indices[i + 1] or indices[i + 1] == indices[i + 2] or indices[i] == indices[i + 2]:
            continue
        if i % 2 == 0:
            faces.append((indices[i], indices[i + 1], indices[i + 2]))
        else:
            faces.append((indices[i + 1], indices[i], indices[i + 2]))
    return faces

@dataclass
class GG2Mesh:
    name: str
    diffuse_texture: str

def _parse_weights(eight_bytes):
    z = list(eight_bytes) + [0]
    target_weight_idx = z[0] * 2
    sum_weights = sum([z[x + 1] for x in range(1, target_weight_idx, 2)])

    if target_weight_idx < len(z):
        z[target_weight_idx] = 255 - sum_weights

    indices = [z[x + 1] for x in range(0, 8, 2)]
    weights = [z[x + 1] for x in range(1, 8, 2)]
    return indices, weights

def build_blender_mesh(mesh_name, vbuf, ibuf, bones_data, target_collection, arm_obj=None):
    """
    Parses vertex and index buffers to generate a Blender mesh with UVs and Vertex Groups.
    Assumes a strict 64-byte stride for the vertex buffer.
    """
    stride = 64
    num_verts = len(vbuf) // stride
    vertices = []

    # 1. Parse Vertex Positions
    for i in range(num_verts):
        vx, vy, vz = struct.unpack_from("<3f", vbuf, i * stride)
        vertices.append((vx, vy, vz))

    # 2. Parse Faces (Assumes _strip_to_triangles exists in your scope)
    faces = _strip_to_triangles(ibuf)

    # 3. Create Blender Objects
    mesh = bpy.data.meshes.new(mesh_name)
    obj = bpy.data.objects.new(mesh_name, mesh)
    target_collection.objects.link(obj)

    mesh.from_pydata(vertices, [], faces)
    mesh.update()

    # 4. Setup UV Map
    uv_layer = mesh.uv_layers.new(name="UVMap")
    for loop in mesh.loops:
        v_idx = loop.vertex_index
        # With a 64-byte stride, the UV offset (stride - 16) is exactly 48
        u, v = struct.unpack_from("<2f", vbuf, (v_idx * stride) + 48)
        uv_layer.data[loop.index].uv = (u, 1.0 - v)

    # 5. Setup Vertex Groups & Weights (if rigged)
    if arm_obj and bones_data:
        # Create vertex groups for all bones beforehand
        for b in bones_data:
            obj.vertex_groups.new(name=b["name"])

        for v_idx in range(num_verts):
            # With a 64-byte stride, the weight offset (stride - 8) is exactly 56
            weight_offset = (v_idx * stride) + 56
            weight_data = vbuf[weight_offset : weight_offset + 8]
            
            # Assumes _parse_weights exists in your scope
            indices, weights = _parse_weights(weight_data)

            for i in range(4):
                if weights[i] > 0 and indices[i] < len(bones_data):
                    bone_name = f"bone_{indices[i]}"
                    vg = obj.vertex_groups.get(bone_name)
                    if vg:
                        vg.add([v_idx], weights[i] / 255.0, "REPLACE")

        # Parent mesh to armature
        obj.parent = arm_obj
        mod = obj.modifiers.new(type="ARMATURE", name="Armature")
        mod.object = arm_obj

    return obj

def create_blender_mesh_from_afb(name, data=None, target_collection=None):
    if not data:
        return None
    
    if target_collection is None:
        target_collection = bpy.context.collection
    
    mesh_offsets = [(i + 4) for i in _findall(b"MAGR", data)]
    bone_offset = data.find(b"BONE")
    
    arm_obj = None
    bones_data = []

    # BONE
    if bone_offset != -1:
        num_bones = struct.unpack("<I", data[bone_offset + 4 : bone_offset + 8])[0] // 40
        current_offset = bone_offset + 8

        for i in range(num_bones):
            qx, qy, qz, qw = struct.unpack_from("<4f", data, current_offset)
            px, py, pz = struct.unpack_from("<3f", data, current_offset + 16)
            parent_idx = struct.unpack_from("<B", data, current_offset + 32)[0]

            quat = mathutils.Quaternion((qw, qx, qy, qz))
            loc = mathutils.Vector((px, py, pz))
            local_matrix = mathutils.Matrix.Translation(loc) @ quat.to_matrix().to_4x4()

            bones_data.append({"name": f"bone_{i}", "parent": parent_idx, "local_matrix": local_matrix})
            current_offset += 40

        arm_data = bpy.data.armatures.new(f"{name}_ArmatureData")
        arm_obj = bpy.data.objects.new(f"{name}_Rig", arm_data)
        target_collection.objects.link(arm_obj)

        bpy.context.view_layer.objects.active = arm_obj
        bpy.ops.object.mode_set(mode="EDIT")
        edit_bones = arm_obj.data.edit_bones
        blender_bones = []

        for bd in bones_data:
            b = edit_bones.new(bd["name"])
            b.head = (0, 0, 0)
            b.tail = (0, 1, 0)
            blender_bones.append(b)

        absolute_matrices = {}
        def get_abs_mat(idx):
            if idx in absolute_matrices:
                return absolute_matrices[idx]
            p_idx = bones_data[idx]["parent"]
            loc_mat = bones_data[idx]["local_matrix"]
            if 0 <= p_idx < num_bones and p_idx != idx:
                blender_bones[idx].parent = blender_bones[p_idx]
                abs_mat = get_abs_mat(p_idx) @ loc_mat
            else:
                abs_mat = loc_mat
            absolute_matrices[idx] = abs_mat
            return abs_mat

        for i in range(num_bones):
            blender_bones[i].matrix = get_abs_mat(i)

        bpy.ops.object.mode_set(mode="OBJECT")
    
    # TEXTURES
    
    textures = []
    offset = data.find(b"TXTL")

    if offset != -1:
        offset += 4
        
        # unpack_from reads directly from the buffer at the given offset
        list_size = struct.unpack_from("<I", data, offset)[0]
        offset += 4 # skips lenght
        
        end_offset = offset + list_size
        
        offset += 4 # skip the first TXTF

        while offset < end_offset:
            str_length = struct.unpack_from("<I", data, offset)[0]
            offset += 4 # skip next TXTF or end of list
            
            texture_name = data[offset : offset + str_length].decode("utf-8", errors="ignore")
            textures.append(texture_name)
            print(f"Found texture: {texture_name}")
            
            offset += str_length
            offset += 4 # skip next TXTF or end of list
        
    # MESH
    created_meshes = []
    
    for mesh_idx, mesh_offset in enumerate(mesh_offsets):
        mesh_name = f"{name}_mesh_{mesh_idx}"
        
        # Read Material Data
        material_data_size = struct.unpack("<I", data[mesh_offset + 8 : mesh_offset + 12])[0]
        material_data = data[mesh_offset + 12 : mesh_offset + 12 + material_data_size]
        texture_idx = int.from_bytes(material_data[12:13], byteorder='little')
        texture_idx = texture_idx if texture_idx < 255 else 0
        
        v_offset_base = mesh_offset + 12 + material_data_size
        
        # In case of emergency uncomment this
        # v_offset_base = data.find(b"VRTB", search_start)
        #print(f"Debug: Searching for VRTB starting at {search_start}, found at {v_offset_base}")
        #if v_offset_base == -1:
        #    print(f"Warning: No VRTB found for {mesh_name}")
        #    continue
            
        vbuf_size = struct.unpack("<I", data[v_offset_base + 4 : v_offset_base + 8])[0]
        vbuf = data[v_offset_base + 8 : v_offset_base + 8 + vbuf_size]

        # Locate and Read PIDX (Index Buffer)
        # Search starting right after the VRTB block
        i_offset_base = data.find(b"PIDX", v_offset_base + 8 + vbuf_size)
        if i_offset_base == -1:
            print(f"Warning: No PIDX found for {mesh_name}")
            continue
            
        # Old code logic: offset + 8 is the size block for PIDX
        ibuf_size_bytes = struct.unpack("<I", data[i_offset_base + 8 : i_offset_base + 12])[0]
        ibuf_count = ibuf_size_bytes // 2
        ibuf_start = i_offset_base + 12
        ibuf = struct.unpack(f"<{ibuf_count}H", data[ibuf_start : ibuf_start + ibuf_size_bytes])

        mesh_obj = build_blender_mesh(
            mesh_name=mesh_name, 
            vbuf=vbuf, 
            ibuf=ibuf, 
            bones_data=bones_data, 
            target_collection=target_collection, 
            arm_obj=arm_obj
        )
        
        mesh = {"mesh": mesh_obj, "texture_idx": texture_idx}
        
        created_meshes.append(mesh)

    return {"armature": arm_obj, "meshes": created_meshes, "textures": textures}
    






def old_create_blender_mesh_from_afb(name, data=None, target_collection=None):
    if not data:
        return None

    if target_collection is None:
        target_collection = bpy.context.collection

    bs = data
    if bs.find(b"VRTB") == -1:
        print(f"Error: this is not a valid GG2 .afb file.")
        return None

    base_name = name
    v_offsets = [(i + 4) for i in _findall(b"VRTB", bs)]
    i_offsets = [(i + 8) for i in _findall(b"PIDX", bs)]
    b_offset = bs.find(b"BONE")

    arm_obj = None
    bones_data = []
    created_meshes = []

    # BONE BLOCK
    if b_offset != -1:
        num_bones = struct.unpack("<I", bs[b_offset + 4 : b_offset + 8])[0] // 40
        current_offset = b_offset + 8

        for i in range(num_bones):
            qx, qy, qz, qw = struct.unpack_from("<4f", bs, current_offset)
            px, py, pz = struct.unpack_from("<3f", bs, current_offset + 16)
            parent_idx = struct.unpack_from("<B", bs, current_offset + 32)[0]

            quat = mathutils.Quaternion((qw, qx, qy, qz))
            loc = mathutils.Vector((px, py, pz))
            local_matrix = mathutils.Matrix.Translation(loc) @ quat.to_matrix().to_4x4()

            bones_data.append({"name": f"bone_{i}", "parent": parent_idx, "local_matrix": local_matrix})
            current_offset += 40

        arm_data = bpy.data.armatures.new(f"{base_name}_ArmatureData")
        arm_obj = bpy.data.objects.new(f"{base_name}_Rig", arm_data)
        target_collection.objects.link(arm_obj)

        bpy.context.view_layer.objects.active = arm_obj
        bpy.ops.object.mode_set(mode="EDIT")
        edit_bones = arm_obj.data.edit_bones
        blender_bones = []

        for bd in bones_data:
            b = edit_bones.new(bd["name"])
            b.head = (0, 0, 0)
            b.tail = (0, 1, 0)
            blender_bones.append(b)

        absolute_matrices = {}
        def get_abs_mat(idx):
            if idx in absolute_matrices:
                return absolute_matrices[idx]
            p_idx = bones_data[idx]["parent"]
            loc_mat = bones_data[idx]["local_matrix"]
            if 0 <= p_idx < num_bones and p_idx != idx:
                blender_bones[idx].parent = blender_bones[p_idx]
                abs_mat = get_abs_mat(p_idx) @ loc_mat
            else:
                abs_mat = loc_mat
            absolute_matrices[idx] = abs_mat
            return abs_mat

        for i in range(num_bones):
            blender_bones[i].matrix = get_abs_mat(i)

        bpy.ops.object.mode_set(mode="OBJECT")


    # MESH BLOCK
    for mesh_idx in range(len(v_offsets)):
        mesh_name = f"{base_name}_mesh_{mesh_idx}"
        v_offset = v_offsets[mesh_idx]
        vbuf_size = struct.unpack("<I", bs[v_offset : v_offset + 4])[0]
        vbuf = bs[v_offset + 4 : v_offset + 4 + vbuf_size]

        i_offset = i_offsets[mesh_idx]
        ibuf_count = struct.unpack("<I", bs[i_offset : i_offset + 4])[0] // 2
        ibuf = struct.unpack(f"<{ibuf_count}H", bs[i_offset + 4 : i_offset + 4 + (ibuf_count * 2)])

        stride = len(vbuf) // (max(ibuf) + 1)
        vertices = []
        num_verts = len(vbuf) // stride
        for i in range(num_verts):
            vx, vy, vz = struct.unpack_from("<3f", vbuf, i * stride)
            vertices.append((vx, vy, vz))

        faces = _strip_to_triangles(ibuf)

        mesh = bpy.data.meshes.new(mesh_name)
        obj = bpy.data.objects.new(mesh_name, mesh)
        target_collection.objects.link(obj)
        created_meshes.append(obj)

        mesh.from_pydata(vertices, [], faces)
        mesh.update()

        if arm_obj and len(bones_data) > 0:
            for b in bones_data:
                obj.vertex_groups.new(name=b["name"])

        uv_layer = mesh.uv_layers.new(name="UVMap")
        for loop in mesh.loops:
            v_idx = loop.vertex_index
            uv_offset = v_idx * stride + stride - 16
            u, v = struct.unpack_from("<2f", vbuf, uv_offset)
            uv_layer.data[loop.index].uv = (u, 1.0 - v)

        if arm_obj and len(bones_data) > 0:
            for v_idx in range(num_verts):
                weight_offset = v_idx * stride + stride - 8
                weight_data = vbuf[weight_offset : weight_offset + 8]
                indices, weights = _parse_weights(weight_data)

                for i in range(4):
                    if weights[i] > 0 and indices[i] < len(bones_data):
                        bone_name = f"bone_{indices[i]}"
                        vg = obj.vertex_groups.get(bone_name)
                        if vg:
                            vg.add([v_idx], weights[i] / 255.0, "REPLACE")

        if arm_obj:
            obj.parent = arm_obj
            mod = obj.modifiers.new(type="ARMATURE", name="Armature")
            mod.object = arm_obj

    return {"armature": arm_obj, "meshes": created_meshes}

def old_apply_motion_to_armature(armature, motion_data, action_name):
    """Too slow"""
    pose_bones = armature.pose.bones

    if not armature.animation_data:
        armature.animation_data_create()

    if motion_data.track_count != len(pose_bones):
        action = bpy.data.actions.new(name=f"{action_name}-broken")
        return
    
    action = bpy.data.actions.new(name=action_name)
    armature.animation_data.action = action
    

    for track_index, track in enumerate(motion_data.tracks):
        target_bone_name = f"bone_{track_index}"
        pose_bone = pose_bones.get(target_bone_name)

        if pose_bone is None:
            continue

        if pose_bone.parent:
            par = pose_bone.parent
            relative_matrix = par.bone.matrix_local.inverted() @ pose_bone.bone.matrix_local
        else:
            relative_matrix = pose_bone.bone.matrix_local

        for keyframe in track.keyframes:
            if keyframe is None:
                continue
            frame = keyframe.time

            # Apply Rotation
            if keyframe.rotation:
                blender_pose_quat = relative_matrix.inverted().decompose()[1] @ keyframe.rotation.to_blender()
                if blender_pose_quat.w < 0:
                    blender_pose_quat.negate()
                pose_bone.rotation_mode = "QUATERNION"
                pose_bone.rotation_quaternion = blender_pose_quat
                pose_bone.keyframe_insert(data_path="rotation_quaternion", frame=frame)

            # Apply Translation
            if keyframe.translation:
                blender_pose_vec = relative_matrix.inverted() @ keyframe.translation.to_blender()
                pose_bone.location = blender_pose_vec
                pose_bone.keyframe_insert(data_path="location", frame=frame)

            # Apply Scale
            if keyframe.scale:
                blender_pose_scale = keyframe.scale.to_blender()
                pose_bone.scale = blender_pose_scale
                pose_bone.keyframe_insert(data_path="scale", frame=frame)

    action.use_fake_user = True
    return action
