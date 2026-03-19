import struct
import io
import mathutils
from . import config

class Quaternion:
    def __init__(self, x: float, y: float, z: float, w: float):
        self.w = w
        self.x = x
        self.y = y
        self.z = z

    def to_blender(self):
        return mathutils.Quaternion((self.w, self.x, self.y, self.z))

class Vector3:
    def __init__(self, x: float, y: float, z: float):
        self.x = x
        self.y = y
        self.z = z

    def to_blender(self):
        return mathutils.Vector((self.x, self.y, self.z))

class KeyFrame:
    def __init__(self, time: int, rotation: Quaternion, translation: Vector3, scale: Vector3, unk_list):
        self.time = time
        self.rotation = rotation
        self.translation = translation
        self.scale = scale
        self.unk_list = unk_list

class Track:
    def __init__(self, offset: int, key_count):
        self.offset = offset
        self.key_count = key_count
        self.keyframes = []

class CGGS_Motion:
    def __init__(self, animation_len, key_count: int, track_count: int, header_size: int, tracks):
        self.animation_len = animation_len
        self.key_count = key_count
        self.track_count = track_count
        self.header_size = header_size
        self.tracks = tracks

def parse_tracks(f, key_count: int, track_count: int):
    aux = 0
    tracks = []
    for i in range(track_count):
        offset = struct.unpack("<I", f.read(4))[0]
        track_key_count = struct.unpack("<I", f.read(4))[0]
        aux += track_key_count
        tracks.append(Track(offset, track_key_count))
    if aux != key_count:
        print(f"Warning: Sum of track key counts ({aux}) does not match total key count ({key_count})")
    return tracks, aux

def parse_key_frame(f):
    try:
        start_pos = f.tell()
        time = struct.unpack("<H", f.read(2))[0]
        flags_byte = struct.unpack("<B", f.read(1))[0]
        yy_byte = struct.unpack("<B", f.read(1))[0]

        presence_flags = flags_byte & 0x07
        unk_flag_bits = flags_byte >> 3

        rotation_data = None
        scale_data = None
        translation_data = None

        if presence_flags & 0x04:
            q1, q2, q3, q4 = struct.unpack("<ffff", f.read(16))
            rotation_data = Quaternion(q1, q2, q3, q4)

        if presence_flags & 0x01:
            sx, sy, sz = struct.unpack("<fff", f.read(12))
            scale_data = Vector3(sx, sy, sz)

        if presence_flags & 0x02:
            tx, ty, tz = struct.unpack("<fff", f.read(12))
            translation_data = Vector3(tx, ty, tz)

    except struct.error as e:
        print(f"Error reading key frame data at offset {start_pos}: {e}")
        return None
    except EOFError:
        print(f"Error: Reached end of file unexpectedly while reading keyframe data near offset {start_pos}")
        return None

    return KeyFrame(time, rotation_data, translation_data, scale_data, [unk_flag_bits, yy_byte])

def parse_motion_bytes(data: bytes, action_name: str):
    try:
        # 1. Unpack header in bulk
        animationLen, key_count_header = struct.unpack_from("<HH", data, 2)
        track_count = struct.unpack_from("<B", data, 7)[0]
        ten_value, header_size = struct.unpack_from("<II", data, 8)
        
        if ten_value != 16:
            print(f"Warning: Expected value 16 at offset 8, found {ten_value} in {action_name}")
            
        # 2. Parse tracks
        tracks = []
        aux = 0
        offset = 16
        for i in range(track_count):
            t_offset, t_key_count = struct.unpack_from("<II", data, offset)
            offset += 8
            aux += t_key_count
            tracks.append(Track(t_offset, t_key_count))
            
        if aux != key_count_header:
            print(f"Warning: Sum of track key counts ({aux}) does not match total key count ({key_count_header})")

        # 3. Batch parse keyframes using raw offsets (Massive speedup here)
        for track in tracks:
            kf_offset = track.offset
            for _ in range(track.key_count):
                time, flags_byte, yy_byte = struct.unpack_from("<HBB", data, kf_offset)
                kf_offset += 4
                
                presence_flags = flags_byte & 0x07
                unk_list = [flags_byte >> 3, yy_byte]
                
                rot = trans = scale = None
                
                if presence_flags & 0x04:
                    q1, q2, q3, q4 = struct.unpack_from("<ffff", data, kf_offset)
                    # GG2 uses x,y,z,w - Mathutils expects w,x,y,z
                    rot = mathutils.Quaternion((q4, q1, q2, q3)) 
                    kf_offset += 16
                if presence_flags & 0x01:
                    sx, sy, sz = struct.unpack_from("<fff", data, kf_offset)
                    scale = mathutils.Vector((sx, sy, sz))
                    kf_offset += 12
                if presence_flags & 0x02:
                    tx, ty, tz = struct.unpack_from("<fff", data, kf_offset)
                    trans = mathutils.Vector((tx, ty, tz))
                    kf_offset += 12
                    
                track.keyframes.append(KeyFrame(time, rot, trans, scale, unk_list))

        return CGGS_Motion(animationLen, key_count_header, track_count, header_size, tracks)

    except struct.error as e:
        print(f"Error reading key frame data in {action_name}: {e}")
        return None
    except Exception as e:
        print(f"Error parsing motion bytes for {action_name}: {e}")
        return None

class Entry:
    def __init__(self, idx):
        self.index = idx
        self.name = None
        self.motIndex = None
        self.pkmnumber = None
        self.colorNumber = None
        self.modelname = None
        self.texturename = None
        self.texturecname = None
        self.normalname = None
        self.mixname = None
        self.asbname = None
        self.unk5 = None
        self.colorVariationSource = None #Used in color variations entries to point to the one with the model
    
    def get_model_name(self):
        return self.modelname if self.modelname else (self.colorVariationSource.modelname if self.colorVariationSource else None)
    
    def get_texturec_name(self):
        return self.texturecname if self.texturecname else (self.colorVariationSource.texturecname if self.colorVariationSource else None)
    
    def get_normal_name(self):
        return self.normalname if self.normalname else (self.colorVariationSource.normalname if self.colorVariationSource else None)

    def read_null_terminated_string(self, data, offset):
        if offset == 0:
            return None
        end = data.find(b"\x00", offset)
        if end == -1:
            raise ValueError("Null terminator not found in data.")
        return data[offset:end].decode("utf-8")

    def extract_files_from_pkm(self, pkm_path, indices):
        results = {}
        with open(pkm_path, "rb") as f:
            header_data = f.read(16)
            magic, filecount, c103, pkm_type, extra = struct.unpack("<4sIIHH", header_data)

            if pkm_type != 0x03:
                print(f"Warning: Unexpected PKM type {pkm_type} in {pkm_path.name}. Expected 0x03.")
                return results

            entries_end = 0x10 + (filecount * 8)
            data_start_offset = (entries_end + 63) & ~63

            for index in indices:
                if index < 0 or index >= filecount:
                    print(f"Warning: Index {index} is out of bounds (Total files: {filecount}).")
                    continue

                f.seek(0x10 + (index * 8))
                entry_offset, entry_size = struct.unpack("<II", f.read(8))
                f.seek(data_start_offset + entry_offset)
                results[index] = f.read(entry_size)
        return results

    def extract_file_from_pkm(self, pkm_path, index):
        result = self.extract_files_from_pkm(pkm_path, [index])
        return result.get(index)

    def extract_files(self):
        out = {}
        if self.texturename:
            td_path = config.DATA_PATH / f"TD{self.pkmnumber}{self.colorNumber}.PKM"
            if td_path.exists():
                out["texture"] = self.extract_file_from_pkm(td_path, self.index)
        target_entry = self.colorVariationSource if self.colorVariationSource else self
        if target_entry.modelname:
            af_path = config.DATA_PATH / f"AF{target_entry.pkmnumber}.PKM"
            if af_path.exists():
                out["model"] = target_entry.extract_file_from_pkm(af_path, target_entry.index)
            if target_entry.texturecname and af_path.exists():
                out["combined_data"] = target_entry.extract_file_from_pkm(af_path, target_entry.index + 1204)
            if target_entry.normalname and af_path.exists():
                out["normal"] = target_entry.extract_file_from_pkm(af_path, target_entry.index + 1204 * 2)
        if target_entry.asbname:
            asb_path = config.DATA_PATH / f"ASB.PKM"
            if asb_path.exists():
                out["asb"] = target_entry.extract_file_from_pkm(asb_path, target_entry.index)
                print(f"Extracted {target_entry.asbname} from {asb_path}")
        return out

    def get_animations(self):
        out = []
        mix_data_map = []
        target_entry = self.colorVariationSource if self.colorVariationSource else self

        if target_entry.mixname:
            mix_path = config.DATA_PATH / "MIX.PKM"
            if mix_path.exists():
                mix_bytes = target_entry.extract_file_from_pkm(mix_path, target_entry.index)

                if mix_bytes and len(mix_bytes) >= 2:
                    for i in range(2, len(mix_bytes) - 1, 2):
                        val = struct.unpack("<H", mix_bytes[i : i + 2])[0]
                        if val != 0xFFFF:
                            slot_index = (i // 2) - 1
                            mix_data_map.append((slot_index, val))

        if not mix_data_map:
            return out

        unique_mot_indices = list(set(pair[1] for pair in mix_data_map))

        if target_entry.motIndex is not None and target_entry.motIndex < len(config.MOTS):
            mot_pkm_path = config.GG2_PATH / "data" / "obj" / f"{config.MOTS[target_entry.motIndex]}"
            batch_results = target_entry.extract_files_from_pkm(mot_pkm_path, unique_mot_indices)

            for slot, mot_idx in mix_data_map:
                if mot_idx in batch_results:
                    out.append((slot, batch_results[mot_idx]))
                else:
                    print(f"Warning: Motion index {mot_idx} not found in PKM.")
        else:
            print(f"Warning: Invalid motIndex {target_entry.motIndex} for entry {target_entry.name}")

        return out

    def parse(self, data, offset):
        (modeloffset, textoffset, texturecoffset, normaloffset, mixoffset, asboffset) = struct.unpack_from("<6I", data, offset)
        self.name = data[offset + 24 : offset + 28].decode("utf-8").rstrip("\x00")
        (self.motIndex, self.pkmnumber, self.colorNumber, self.filepath_offset, self.unk5) = struct.unpack_from("<5I", data, offset + 28)
        self.modelname = self.read_null_terminated_string(data, 0xCEF0 + modeloffset - 1) if modeloffset != 0 else None
        self.texturename = self.read_null_terminated_string(data, 0xCEF0 + textoffset - 1) if textoffset != 0 else None
        self.texturecname = self.read_null_terminated_string(data, 0xCEF0 + texturecoffset - 1) if texturecoffset != 0 else None
        self.normalname = self.read_null_terminated_string(data, 0xCEF0 + normaloffset - 1) if normaloffset != 0 else None
        self.mixname = self.read_null_terminated_string(data, 0xCEF0 + mixoffset - 1) if mixoffset != 0 else None
        self.asbname = self.read_null_terminated_string(data, 0xCEF0 + asboffset - 1) if asboffset != 0 else None
    

def parse_list(path):
    with open(path, "rb") as f:
        if f.read(4) != b"\xB4\x04\x00\x00":
            raise ValueError("Invalid loadlist.bin file: Missing expected header.")
        data = f.read()

    entries = []
    last_entry = None
    for i in range(1204):
        entry = Entry(i)
        entry.parse(data, i * 44)
        if last_entry and entry.name == last_entry.name:
            entry.colorVariationSource = last_entry
            entries.append(entry)
            continue
        entries.append(entry)
        last_entry = entry

    return entries