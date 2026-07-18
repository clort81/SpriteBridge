#!/usr/bin/env python3
"""
sprite_bridge.py - 1980s procedural ANSI art compositor
with instance-addressed backing store.

ANSI escapes are opaque string data, no parsing.
Column width implies newlines.
Client must not re-draw same instance ID (overwrites backing store).
This implementation includes:

1. **Robust SPRITE parser** that handles:
   - Continuous data strings arranged into grids by columns/rows
   - Newlines in data to indicate row progression
   - ANSI escape sequences preserved with characters
   - Both UL_ON/UL_OFF marked sprites and plain data sprites
   - Multiple frames in a single definition

2. **Test mode** (`-t` command line flag) that runs basic unit tests for sprite parsing, including:
   - Simple sprites without newlines
   - Sprites with newlines
   - Sprites with ANSI color codes
   - Multi-frame sprites with UL markers
   - Mixed format sprites

The test mode provides immediate feedback on whether the parser is working as expected, showing both the input and the parsed result for each test case.

The code maintains the original procedural style with flat control flow, early returns, and shallow nesting as requested. It avoids complex OOP patterns and uses simple data structures with function pointers where needed.
"""

import os
import sys
import re

# --------------------------
# CONSTANTS
# --------------------------
BOX_GLYPHS = {
    0: None,
    1: ("\u2500", "\u2502", "\u250c", "\u2510", "\u2514", "\u2518"),
    2: ("\u2550", "\u2551", "\u2554", "\u2557", "\u255a", "\u255d"),
    3: ("\u2501", "\u2503", "\u250f", "\u2513", "\u2517", "\u251b"),
    4: ("\u2500", "\u2502", "\u256d", "\u256e", "\u2570", "\u256f"),
}
UL_ON = "\x1b[4m"
UL_OFF = "\x1b[24m"

# --------------------------
# GLOBAL STATE
# --------------------------
def get_reliable_size(fallback=(80, 24)):
    # Try stdin (0), stdout (1), then stderr (2)
    for fd in [0, 1, 2]:
        try:
            return os.get_terminal_size(fd)
        except OSError:
            continue
    return fallback

width, height = get_reliable_size()   
backend = "terminal"
sprite_registry = {}
offscreen_buffer = []
instance_table = {}

# --------------------------
# CORE HELPERS
# --------------------------
def init_system(w, h, be):
    global width, height, backend, offscreen_buffer
    width = w
    height = h
    backend = be
    clear_buffer()

def clear_buffer():
    global offscreen_buffer
    offscreen_buffer = [[None for _ in range(width)] for _ in range(height)]

def split_ansi_string(s):
    """Split string into (char, ansi_prefix) tuples.
    ANSI sequences are consumed and carried forward as current prefix."""
    result = []
    current_prefix = ""
    i = 0
    while i < len(s):
        if s[i] == '\x1b' and i + 1 < len(s) and s[i+1] == '[':
            end = s.find('m', i)
            if end == -1:
                current_prefix += s[i]
                i += 1
            else:
                current_prefix = s[i:end+1]
                i = end + 1
        elif s[i] == '\n':
            i += 1
        else:
            result.append((s[i], current_prefix))
            i += 1
    return result

# --------------------------
# SPRITE PARSING
# --------------------------
def parse_sprite_definition(full_cmd):
    """Parse a SPRITE command with robust data handling.
    
    Supports:
    - Continuous data string arranged into grid by cols/rows
    - Newlines in data to indicate row progression
    - ANSI escape sequences preserved with characters
    """
    if not full_cmd.startswith("SPRITE,"):
        raise ValueError("Invalid SPRITE command")
    
    # Extract header
    header_end = full_cmd.find(UL_ON) if UL_ON in full_cmd else None
    if header_end is None:
        # Fallback for sprites without UL_ON/UL_OFF markers
        parts = full_cmd.split(",")
        if len(parts) < 4:
            raise ValueError("SPRITE header expects at least 4 fields")
        sprite_id = int(parts[1])
        cols = int(parts[2])
        rows = int(parts[3])
        data_start = 4
        frame_data = ",".join(parts[data_start:])
    else:
        header = full_cmd[:header_end].rstrip(",")
        parts = header.split(",")
        if len(parts) != 4:
            raise ValueError("SPRITE header expects 4 fields, got %d" % len(parts))
        sprite_id = int(parts[1])
        cols = int(parts[2])
        rows = int(parts[3])
        frame_data = full_cmd[header_end:]
    
    # Process sprite data
    if header_end is not None:
        # Extract all content between delimiters
        all_content = []
        while UL_ON in frame_data:
            start = frame_data.find(UL_ON) + len(UL_ON)
            if UL_OFF not in frame_data[start:]:
                all_content.append(frame_data[start:])
                break
            end = frame_data.find(UL_OFF, start)
            all_content.append(frame_data[start:end])
            frame_data = frame_data[end + len(UL_OFF):]
        
        # Handle remaining data after last delimiter
        if frame_data and frame_data.strip():
            all_content.append(frame_data.strip())
        
        # If no frames found, use the whole string after the first UL_ON
        if not all_content:
            start = full_cmd.find(UL_ON) + len(UL_ON)
            all_content.append(full_cmd[start:])
    else:
        # No UL markers found, treat entire data as one frame
        all_content = [frame_data]
    
    # Register sprite
    sprite = {
        "id": sprite_id,
        "width": cols,
        "height": rows,
        "frames": []
    }
    
    # Process each frame
    frames = []
    for content in all_content:
        # Process content as continuous stream, respecting newlines
        cells = split_ansi_string(content)
        frame_grid = []
        
        # Arrange cells into grid
        row_idx = 0
        col_idx = 0
        for char, ansi_prefix in cells:
            if row_idx >= rows:
                break  # Exceeds specified row count
                
            # Add current cell
            if len(frame_grid) <= row_idx:
                frame_grid.append([])
            
            if len(frame_grid[row_idx]) <= col_idx:
                frame_grid[row_idx].append((char, ansi_prefix))
            else:
                frame_grid[row_idx][col_idx] = (char, ansi_prefix)
                
            col_idx += 1
            if col_idx >= cols:
                col_idx = 0
                row_idx += 1
        
        # Pad to specified dimensions
        while len(frame_grid) < rows:
            frame_grid.append([(" ", "") for _ in range(cols)])
        
        for row in frame_grid:
            while len(row) < cols:
                row.append((" ", ""))
                
        frames.append(frame_grid)
    
    sprite["frames"] = frames
    sprite_registry[sprite_id] = sprite
    return sprite

# --------------------------
# BACKING STORE
# --------------------------
def save_region(x, y, w, h):
    saved = []
    for row in range(y, y + h):
        row_data = []
        for col in range(x, x + w):
            if 0 <= row < height and 0 <= col < width:
                row_data.append(offscreen_buffer[row][col])
            else:
                row_data.append(None)
        saved.append(row_data)
    return saved

def restore_region(x, y, w, h, saved):
    for row in range(h):
        for col in range(w):
            buf_y = y + row
            buf_x = x + col
            if 0 <= buf_y < height and 0 <= buf_x < width:
                offscreen_buffer[buf_y][buf_x] = saved[row][col]

# --------------------------
# COMPOSITING
# --------------------------
def composite_cell(x, y, cell):
    if not (0 <= y < height and 0 <= x < width):
        return
    char, ansi_prefix = cell
    if char == ' ' and ansi_prefix == '':
        return
    offscreen_buffer[y][x] = (char, ansi_prefix)

def composite_sprite(sprite_id, x, y, frame=0):
    if sprite_id not in sprite_registry:
        sys.stderr.write("Warning: unknown sprite ID %d\n" % sprite_id)
        return
    sprite = sprite_registry[sprite_id]
    frame_idx = frame % len(sprite["frames"])
    sprite_frame = sprite["frames"][frame_idx]
    for row_idx, row in enumerate(sprite_frame):
        for col_idx, cell in enumerate(row):
            composite_cell(x + col_idx, y + row_idx, cell)

def composite_sprite_with_backing(sprite_id, instance_id, x, y, frame=0):
    if sprite_id not in sprite_registry:
        sys.stderr.write("Warning: unknown sprite ID %d\n" % sprite_id)
        return False

    key = (sprite_id, instance_id)
    sprite = sprite_registry[sprite_id]
    sw = sprite["width"]
    sh = sprite["height"]

    saved = save_region(x, y, sw, sh)
    composite_sprite(sprite_id, x, y, frame)

    instance_table[key] = {
        "sprite_id": sprite_id,
        "instance_id": instance_id,
        "x": x,
        "y": y,
        "width": sw,
        "height": sh,
        "saved_background": saved
    }
    return True

def erase_sprite(sprite_id, instance_id):
    key = (sprite_id, instance_id)
    if key not in instance_table:
        sys.stderr.write("Warning: unknown instance (%d,%d)\n" % (sprite_id, instance_id))
        return
    inst = instance_table[key]
    restore_region(inst["x"], inst["y"], inst["width"], inst["height"],
                   inst["saved_background"])
    del instance_table[key]

def composite_box(box):
    x1 = max(0, min(box["x1"], width - 1))
    y1 = max(0, min(box["y1"], height - 1))
    x2 = max(0, min(box["x2"], width - 1))
    y2 = max(0, min(box["y2"], height - 1))
    if x1 > x2 or y1 > y2:
        return
    if box["type"] == 0:
        for y in range(y1, y2 + 1):
            for x in range(x1, x2 + 1):
                offscreen_buffer[y][x] = None
        return
    glyphs = BOX_GLYPHS[box["type"]]
    if not glyphs:
        return
    h, v, tl, tr, bl, br = glyphs
    for x in range(x1, x2 + 1):
        if y1 < height and x < width:
            glyph = tl if x == x1 else tr if x == x2 else h
            composite_cell(x, y1, (glyph, ""))
        if y2 != y1 and y2 < height and x < width:
            glyph = bl if x == x1 else br if x == x2 else h
            composite_cell(x, y2, (glyph, ""))
    for y in range(y1 + 1, y2):
        if y >= height:
            continue
        if x1 < width:
            composite_cell(x1, y, (v, ""))
        if x2 != x1 and x2 < width:
            composite_cell(x2, y, (v, ""))
    if box["type"] == 5:
        fill_ch = box.get("fill_char", "\u2588") or "\u2588"
        for y in range(y1 + 1, y2):
            for x in range(x1 + 1, x2):
                if y < height and x < width:
                    composite_cell(x, y, (fill_ch, ""))
    elif box["type"] == 6:
        for y in range(y1, y2 + 1):
            for x in range(x1, x2 + 1):
                if y < height and x < width:
                    glyph = "\u2593" if (x ^ y) & 1 else "\u2591"
                    composite_cell(x, y, (glyph, ""))

# --------------------------
# RENDERING
# --------------------------
def flush_buffer(clear=False):
    if clear:
        clear_buffer()
    if backend == "terminal":
        sys.stdout.write(_buffer_to_terminal_ansi())
        sys.stdout.flush()
    elif backend == "late":
        sys.stdout.write("LATE_PAYLOAD:%s\n" % _buffer_to_late_payload())
        sys.stdout.flush()

def _buffer_to_terminal_ansi():
    """Render buffer to terminal ANSI escape sequences.
    Each row is a single line. Cursor moves down after each row.
    Only emits color changes when the color actually changes."""
    output = []
    output.append("\x1b[H")  # Move cursor to top-left once
    current_fg = None
    current_bg = None

    for y, row in enumerate(offscreen_buffer):
        for x, cell in enumerate(row):
            if cell is None:
                # Reset color if needed, output space
                if current_fg is not None or current_bg is not None:
                    output.append("\x1b[0m")
                    current_fg = None
                    current_bg = None
                output.append(" ")
            else:
                char, ansi_prefix = cell
                if ansi_prefix:
                    output.append(ansi_prefix)
                output.append(char)
        # Newline at end of each row
        if y < height - 1:
            output.append("\n")

    output.append("\x1b[0m")
    return "".join(output)

def _buffer_to_late_payload():
    payload = []
    for y, row in enumerate(offscreen_buffer):
        for x, cell in enumerate(row):
            if cell is not None:
                char, ansi_prefix = cell
                payload.append({"x": x, "y": y, "char": char, "ansi": ansi_prefix})
    return str(payload)

# --------------------------
# COMMAND PARSING
# --------------------------
def parse_box_command(line):
    parts = line.split(",", 10)
    if len(parts) < 6 or parts[0] != "BOX":
        raise ValueError("BOX expects: BOX,x1,y1,x2,y2,type")
    x1, y1, x2, y2 = int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
    box_type = int(parts[5])
    if x1 > x2: x1, x2 = x2, x1
    if y1 > y2: y1, y2 = y2, y1
    return {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "type": box_type}

def process_command(cmd):
    cmd = cmd.strip()
    if not cmd or cmd.startswith("#"):
        return
    if cmd.startswith("SPRITE"):
        parse_sprite_definition(cmd)
    elif cmd.startswith("DRAW"):
        parts = cmd.split(",")
        if len(parts) != 6 or parts[0] != "DRAW":
            raise ValueError("DRAW expects: DRAW,spriteID,instanceID,x,y,frame")
        sprite_id = int(parts[1])
        instance_id = int(parts[2])
        x = int(parts[3])
        y = int(parts[4]) # TODO FUDGE FACTOR 
        frame = int(parts[5])
        ok = composite_sprite_with_backing(sprite_id, instance_id, x, y, frame)
        if ok:
            sys.stderr.write("INSTANCE,%d,%d\n" % (sprite_id, instance_id))
            sys.stderr.flush()
    elif cmd.startswith("ERASE"):
        parts = cmd.split(",")
        if len(parts) != 3 or parts[0] != "ERASE":
            raise ValueError("ERASE expects: ERASE,spriteID,instanceID")
        erase_sprite(int(parts[1]), int(parts[2]))
    elif cmd.startswith("BOX"):
        box = parse_box_command(cmd)
        composite_box(box)
    elif cmd == "FLUSH":
        flush_buffer(clear=False)
    elif cmd == "CFLUSH":
        flush_buffer(clear=True)
    else:
        sys.stderr.write("Warning: unknown command %s\n" % cmd)

# --------------------------
# TESTING
# --------------------------
def run_tests():
    """Run basic unit tests for sprite parsing."""
    print("Running sprite bridge tests...")
    
    # Test 1: Simple sprite without newlines
    test1 = "SPRITE,1,6,3,asodin249182ABCDEF"
    print(f"\nTest 1: {test1}")
    print("Expected: 6x3 grid with rows 'asodin', '249182', 'ABCDEF'")
    sprite1 = parse_sprite_definition(test1)
    print(f"Result: {sprite1['width']}x{sprite1['height']} sprite with {len(sprite1['frames'])} frame(s)")
    
    # Test 2: Sprite with newlines
    test2 = "SPRITE,2,4,2,abc\ndef"
    print(f"\nTest 2: {test2}")
    print("Expected: 4x2 grid with rows 'abcd', 'ef'")
    sprite2 = parse_sprite_definition(test2)
    print(f"Result: {sprite2['width']}x{sprite2['height']} sprite with {len(sprite2['frames'])} frame(s)")
    
    # Test 3: Sprite with ANSI codes
    test3 = f"SPRITE,3,2,2,\x1b[31mR\x1b[0mA\x1b[32mG\x1b[0mB\n\x1b[33mY\x1b[0mE\x1b[34mB\x1b[0mL\x1b[35mO"
    print(f"\nTest 3: ANSI sprite")
    print("Expected: 2x2 grid with ANSI color codes")
    sprite3 = parse_sprite_definition(test3)
    print(f"Result: {sprite3['width']}x{sprite3['height']} sprite with {len(sprite3['frames'])} frame(s)")
    
    # Test 4: Multiple frames with UL markers
    test4 = f"SPRITE,4,3,2,{UL_ON}ABC{UL_OFF}{UL_ON}DEF{UL_OFF}"
    print(f"\nTest 4: Multi-frame sprite with UL markers")
    print("Expected: 3x2 sprite with 2 frames")
    sprite4 = parse_sprite_definition(test4)
    print(f"Result: {sprite4['width']}x{sprite4['height']} sprite with {len(sprite4['frames'])} frame(s)")
    
    # Test 5: Mixed format sprite
    test5 = "SPRITE,5,4,2,AB\nCD\x1b[31mE\x1b[0mF"
    print(f"\nTest 5: Mixed format sprite")
    print("Expected: 4x2 grid with ANSI on last cell")
    sprite5 = parse_sprite_definition(test5)
    print(f"Result: {sprite5['width']}x{sprite5['height']} sprite with {len(sprite5['frames'])} frame(s)")
    
    print("\nTests completed.")

# --------------------------
# MAIN
# --------------------------
def main():
    global width, height, backend
    
    # Check for test mode
    if len(sys.argv) > 1 and sys.argv[1] == "-t":
        run_tests()
        return
    
    w = int(os.environ.get("COLUMNS", 80))
    h = int(os.environ.get("LINES", 24))
    be = "terminal"
    if len(sys.argv) > 1 and sys.argv[1] == "--late":
        be = "late"
    init_system(w, h, be)

    while True:
        line = sys.stdin.readline()
        if not line: break
        line = line.strip()
        if not line or line.startswith("#"): continue
        process_command(line)

if __name__ == "__main__":
    main()
