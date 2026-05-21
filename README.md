# Guilty Gear 2: Overture — Blender Loadlist Importer

A Blender Add-on designed to import character rigs, meshes, textures, animations, and attached models directly from **Guilty Gear 2: Overture** using the game's `loadtable.bin` database.

Developed and tested for Blender 4.5.0 but its compatible with more recent Blender versions.

---

## What does it do

- **Automated Registry Parsing**: Reads and parses `loadtable.bin` to populate a list of all game entries.
- **Archive Extraction (`.PKM`)**: Dynamically extracts AFB mesh data files, ASL scripts, texture packages, and animation tracks out of custom PKM archives (`AF*.PKM`, `TD*.PKM`, `ASB.PKM`, `MIX.PKM`, and motion archives).
- **ASB Script Extras Parsing**: Inspects the compiled bytecode inside character `ASB` scripts looking for the `OnCreate` function to identify attached models (weapons and other stuff). The importer prompts you to import these extras and automatically attaches them to the correct skeletal joints via Blender constraints.
- **Automated Materials & Textures**:
  - Matches diffuse textures, normal maps (`0N.XT`), and combined maps (`0C.XT`).
  - Builds materials with all textures automatically assigned and linked.
- **Skeletal Animations (`.PKM` / Motion Files)**:
  - Imports animation data from `MIX.PKM` and each model related motion archive.
  - Automatically loads and assigns all parsed animations to the imported rig.

---

## Installation

1. Download  the realease or clone this directory as a folder named `gg2_importer` and zip it.
2. In Blender, go to **Edit** $\to$ **Preferences** $\to$ **Add-ons** $\to$ **Install...**
3. Select `gg2_importer.zip` and enable it.
4. In the Add-on settings, specify the path to your **Guilty Gear 2 Overture** installation directory (Where the `loadtable.bin` is) (defaults to the standard Steam path: `C:\Program Files (x86)\Steam\steamapps\common\GG2`).

---

## How to Use

1. Navigate to **File** $\to$ **Import** $\to$ **Guilty Gear 2 Overture Loadlist (.bin)**.
2. The addon will parse `loadtable.bin` and open the **Entry Selector** dialog.
<img width="787" height="332" alt="image" src="https://github.com/user-attachments/assets/b2c20cea-be9d-4066-a722-449c5c29dfbf" />

4. Select your target entry and hit **OK**.
5. If the model is related to other models vi ASL (weapons, accessories, etc.), an **Extra Import Options** dialog will open:
   - Check the extras you want to include (along with the bone index they will bind to).
   - Press **OK** to execute the import.
<img width="631" height="200" alt="image" src="https://github.com/user-attachments/assets/f6d7ef47-5d80-4c5b-ab17-e1ccee6a982f" />

6. The addon will automatically import the character rig, parent the meshes, construct material nodes, resolve DDS textures, bind extras, and populate the Action Editor with the character's full suite of animations.

To view the multiple animations of a character
1. Go to any tab (I normaly use the lower timeline) and change the Timeline tab to "Dope Sheet"
2. Switch the "Dope Sheet" mode to "Action Editor" mode.
3. Select the action from the dropdown menu.

<img width="584" height="263" alt="image" src="https://github.com/user-attachments/assets/04f87c3f-9ba2-4e04-93e7-13cfd15e4a66" />

---
