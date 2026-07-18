# SpriteBridge: *printf your game!*

A lightweight, procedural ANSI art compositor for terminal-based games and applications. Sprite Bridge provides a simple command-based API for managing sprites with automatic backing store restoration, making it ideal for terminal games, BBS doors, and retro-style applications.

![SpriteBridge Demo](https://github.com/clort81/SpriteBridge/blob/main/fishtank_spritebridge.gif)

## Features

- **Instance-Addressed Sprites**: Draw and erase sprites without manually managing what's underneath
- **ANSI Color Support**: Full support for ANSI escape sequences in sprite definitions
- **Automatic Backing Store**: Saves and restores screen regions automatically
- **Procedural Design**: Simple, flat control flow inspired by 1980s programming aesthetics
- **Multiple Output Backends**: Terminal (ANSI) or structured payload format
- **Box Drawing**: Built-in support for box-drawing characters and decorations

## How It Works

Sprite Bridge maintains an offscreen buffer and an instance table. When you `DRAW` a sprite:

1. It saves the current screen region (backing store)
2. Composites the sprite onto the buffer
3. Stores the saved region in the instance table keyed by `(sprite_id, instance_id)`

When you `ERASE` a sprite:

1. It retrieves the saved backing store
2. Restores the original screen region
3. Removes the instance from the table

This allows clean sprite management without full-screen redraws or manual dirty rectangle tracking.

## API Commands

All commands are sent via stdin, one per line.

### SPRITE

Define a sprite graphic.

```
SPRITE,<id>,<cols>,<rows>,<data>
```

- `id`: Unique sprite identifier (integer)
- `cols`: Width in characters
- `rows`: Height in characters  
- `data`: Sprite pixel data (continuous string or newline-separated rows)

**Example:**
```bash
SPRITE,1,4,3,####\n####\n####
SPRITE,2,2,2,\033[31mAA\033[0m\nBB
```

**With underline markers (multi-frame):**
```bash
SPRITE,3,3,2,\033[4mABC\033[24m\033[4mDEF\033[24m
```

### DRAW

Draw a sprite instance at a position.

```
DRAW,<sprite_id>,<instance_id>,<x>,<y>,<frame>
```

- `sprite_id`: Reference to a defined sprite
- `instance_id`: Unique instance identifier (you manage this)
- `x`: Column position (0-indexed)
- `y`: Row position (0-indexed)
- `frame`: Frame index for multi-frame sprites (0-indexed)

**Example:**
```bash
DRAW,1,100,10,5,0    # Draw sprite 1 as instance 100 at (10,5)
DRAW,1,101,15,5,0    # Draw same sprite as different instance at (15,5)
```

### ERASE

Remove a sprite instance and restore the background.

```
ERASE,<sprite_id>,<instance_id>
```

- `sprite_id`: The sprite type
- `instance_id`: The specific instance to remove

**Example:**
```bash
ERASE,1,100    # Erase instance 100 of sprite 1
```

### BOX

Draw a box/rectangle decoration.

```
BOX,<x1>,<y1>,<x2>,<y2>,<type>[,<fill_char>]
```

- `x1,y1`: Top-left corner
- `x2,y2`: Bottom-right corner
- `type`: Box style (0=clear, 1-4=different border styles, 5=filled, 6=checkerboard)
- `fill_char`: Optional fill character for type 5

**Example:**
```bash
BOX,0,0,79,24,1          # Single-line border around screen
BOX,10,10,20,15,5,#      # Filled box with # character
BOX,0,0,79,24,0          # Clear entire screen
```
### CLEAR

Clear the ofscreen buffer, sprite instances remain unaffected, just their stamps are erased.

```
CFLUSH
```

### FLUSH

Render the current buffer to the terminal without clearing.

```
FLUSH
```

### CFLUSH

Clear the buffer and render to the terminal.

```
CFLUSH
```

## Usage

### Basic Terminal Mode

```bash
# Run interactively
python3 sprite_bridge.py

# Or pipe commands
echo -e "SPRITE,1,2,2,##\n##\nDRAW,1,1,10,10,0\nFLUSH" | python3 sprite_bridge.py
```

### Late Backend (Structured Output)

```bash
python3 sprite_bridge.py --late
```

Outputs JSON-like payload to stdout instead of ANSI escapes.

### Test Mode

```bash
python3 sprite_bridge.py -t
```

Runs built-in unit tests for sprite parsing.

## Integration Example

### Bash Script

```bash
#!/bin/bash
# fish.sh - Simple animated fish demo

BRIDGE="./sprite_bridge.py"

# Define sprite
echo "SPRITE,1,6,3,>>AA<<\n>>BB<<\n>>CC<<"

# Draw at position
echo "DRAW,1,1,5,10,0"

# Update position
echo "ERASE,1,1"
echo "DRAW,1,1,6,10,0"

# Render
echo "FLUSH"
```

### C Integration

```c
#include <stdio.h>
#include <stdlib.h>

int main() {
    FILE* bridge = popen("python3 sprite_bridge.py", "w");
    
    // Define sprite
    fprintf(bridge, "SPRITE,0,4,2,####\n####\n");
    
    // Draw sprite
    fprintf(bridge, "DRAW,0,1,10,5,0\n");
    
    // Flush to terminal
    fprintf(bridge, "FLUSH\n");
    fflush(bridge);
    
    // Later, erase it
    fprintf(bridge, "ERASE,0,1\n");
    fprintf(bridge, "FLUSH\n");
    fflush(bridge);
    
    pclose(bridge);
    return 0;
}
```

## Why Use Sprite Bridge?

I had a sdl game that was rendering 2d sprites to a sdl window and i wanted something where the game could just printf draw commands to another program to render to terminal.

## Limitations

- Sprites overlap in-order (later draws overwrite earlier ones in the buffer)
- Unique Sprite Instance IDs must be declared by calling program and unique per sprite type, Sprite 2, Instance 521, Sprite 2, Instance 522 share the same sprite base-type but different backing stores and potentially other information.
- Terminal should support ANSI escape sequences, preferably ECMA-48 full 24-bit RGB
- No automatic collision detection (manage in the calling application)

## License

MIT. Use freely for your terminal projects. Accredation to clort + help from GLM, Qwen and MiMo.

