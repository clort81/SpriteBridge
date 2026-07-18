#!/usr/bin/env bash
# fishtank.sh - procreating fish demo with two fish sizes + rising bubbles
# Demonstrates sprite_bridge.py's type/instance architecture

PROG="./sprite_bridge.py"
ESC=$'\x1b'
COLS=$(tput cols)
LINES=$(tput lines)

# ============================================================
#  FISH ENTITIES
# ============================================================
MAX_FISH=255
declare -a FX FY FDX FDY FCOLOR FTYPE   # FTYPE: 0=big, 1=small
FISH_COUNT=0

# ============================================================
#  BUBBLE ENTITIES
# ============================================================
MAX_BUBBLES=32
declare -a BX BY BACTIVE
BUBBLE_SPAWN_COUNTER=0
BUBBLE_SPAWN_INTERVAL=8   # spawn a bubble every N frames (~2.5/sec at 30fps)

# ============================================================
#  PERFORMANCE TRACKING
# ============================================================
TARGET_FPS=30
FRAME_COUNT=0
START_TIME=$(date +%s%N)
DRIFT_PERCENT=0

# ============================================================
#  ANSI COLORS (20 colors for fish)
# ============================================================
FISH_COLORS=(
    "${ESC}[38;2;255;0;0m"     # Red
    "${ESC}[38;2;0;255;0m"     # Green
    "${ESC}[38;2;0;0;255m"     # Blue
    "${ESC}[38;2;255;255;0m"   # Yellow
    "${ESC}[38;2;255;0;255m"   # Magenta
    "${ESC}[38;2;0;255;255m"   # Cyan
    "${ESC}[38;2;255;128;0m"   # Orange
    "${ESC}[38;2;128;0;255m"   # Purple
    "${ESC}[38;2;0;128;0m"     # Dark green
    "${ESC}[38;2;128;128;128m" # Gray
    "${ESC}[38;2;255;192;203m" # Pink
    "${ESC}[38;2;165;42;42m"   # Brown
    "${ESC}[38;2;0;0;128m"     # Navy
    "${ESC}[38;2;128;0;0m"     # Maroon
    "${ESC}[38;2;0;128;128m"   # Teal
    "${ESC}[38;2;128;128;0m"   # Olive
    "${ESC}[38;2;75;0;130m"    # Indigo
    "${ESC}[38;2;255;20;147m"  # Deep pink
    "${ESC}[38;2;0;255;127m"   # Spring green
    "${ESC}[38;2;255;140;0m"   # Dark orange
)

# ============================================================
#  FISH SPAWNING
# ============================================================
spawn_fish() {
    local x=$1 y=$2 dx=$3 dy=$4 color_idx=$5 ftype=$6
    if [ "$FISH_COUNT" -ge "$MAX_FISH" ]; then return; fi
    FX[$FISH_COUNT]=$x
    FY[$FISH_COUNT]=$y
    FDX[$FISH_COUNT]=$dx
    FDY[$FISH_COUNT]=$dy
    FCOLOR[$FISH_COUNT]=${FISH_COLORS[$color_idx]}
    FTYPE[$FISH_COUNT]=$ftype
    FISH_COUNT=$((FISH_COUNT + 1))
}

# Spawn initial 64 fish (mix of big and small)
for ((i=0; i<64; i++)); do
    x=$((RANDOM % (COLS - 10) + 2))
    y=$((RANDOM % (LINES - 6) + 2))
    dx=$(( (RANDOM % 3) - 1 ))
    dy=$(( (RANDOM % 3) - 1 ))
    if [ $dx -eq 0 ] && [ $dy -eq 0 ]; then dx=1; fi
    color_idx=$((RANDOM % ${#FISH_COLORS[@]}))
    # 60% big fish, 40% small fish
    if [ $((RANDOM % 5)) -lt 3 ]; then
        ftype=0
    else
        ftype=1
    fi
    spawn_fish $x $y $dx $dy $color_idx $ftype
done

# ============================================================
#  BUBBLE SPAWNING
# ============================================================
spawn_bubble() {
    # Find a free slot
    local slot=-1
    for ((i=0; i<MAX_BUBBLES; i++)); do
        if [ "${BACTIVE[$i]}" != "1" ]; then
            slot=$i
            break
        fi
    done
    if [ $slot -eq -1 ]; then return; fi
    
    BX[$slot]=$((RANDOM % (COLS - 4) + 2))
    BY[$slot]=$((LINES - 3))
    BACTIVE[$slot]=1
}

# ============================================================
#  START PERSISTENT BRIDGE
# ============================================================
coproc BRIDGE { python3 "$PROG" 2>> bridge.log > /dev/tty; }

# Send sprite definitions ONCE at startup
{
    # SPRITE 1: Big fish (6x3) - will be redefined per-fish with color
    echo "SPRITE,1,6,3,>>AA<<>>BB<<>>CC<<"
    
    # SPRITE 2: Small fish (2x2) - will be redefined per-fish with color
    echo "SPRITE,2,2,2,><><"
    
    # SPRITE 3: Score display (redefined each frame with width)
    # SPRITE 4: Drift display (redefined each frame with width)
    
    # SPRITE 5: Bubbles (1x3) - light blue, static shape
    echo "SPRITE,5,1,3,${ESC}[96m*${ESC}[96mo${ESC}[96m.${ESC}[0m"
} >&"${BRIDGE[1]}"

# ============================================================
#  MAIN LOOP
# ============================================================
while true; do
    FRAME_COUNT=$((FRAME_COUNT + 1))
    
    # --- Fish reproduction every 15 frames ---
    if [ $((FRAME_COUNT % 15)) -eq 0 ] && [ "$FISH_COUNT" -gt 0 ] && [ "$FISH_COUNT" -lt "$MAX_FISH" ]; then
        IDX=$((RANDOM % FISH_COUNT))
        SX=${FX[$IDX]}; SY=${FY[$IDX]}
        SDX=${FDX[$IDX]}; SDY=${FDY[$IDX]}
        if [ $((RANDOM % 2)) -eq 0 ]; then SDX=$((SDX * -1)); else SDY=$((SDY * -1)); fi
        if [ $((RANDOM % 3)) -eq 0 ]; then SDX=$((SDX * 2)); fi
        # Child inherits parent's type
        spawn_fish "$SX" "$SY" "$SDX" "$SDY" $((RANDOM % ${#FISH_COLORS[@]})) ${FTYPE[$IDX]}
    fi
    
    # --- Bubble spawn timer ---
    BUBBLE_SPAWN_COUNTER=$((BUBBLE_SPAWN_COUNTER + 1))
    if [ $BUBBLE_SPAWN_COUNTER -ge $BUBBLE_SPAWN_INTERVAL ]; then
        BUBBLE_SPAWN_COUNTER=0
        spawn_bubble
    fi
    
    # --- Calculate drift ---
    current_time=$(date +%s%N)
    elapsed_ns=$((current_time - START_TIME))
    elapsed_s_x100=$((elapsed_ns / 10000000))
    if [ $elapsed_s_x100 -gt 0 ]; then
        expected_frames_x100=$((elapsed_s_x100 * TARGET_FPS))
        actual_frames_x100=$((FRAME_COUNT * 100))
        if [ $expected_frames_x100 -gt 0 ]; then
            DRIFT_PERCENT=$(( (actual_frames_x100 - expected_frames_x100) * 100 / expected_frames_x100 ))
        fi
    fi
    
    # --- Build frame ---
    {
        # Clear buffer (no terminal output yet)
        echo "CLEAR"
        
        # Score sprite (fish count)
        SCORE_TEXT=$(printf "FISH: %3d" "$FISH_COUNT")
        SCORE_LEN=${#SCORE_TEXT}
        echo "SPRITE,3,${SCORE_LEN},1,${ESC}[96m${SCORE_TEXT}${ESC}[0m"
        echo "DRAW,3,0,2,1,0"
        
        # Drift sprite
        if [ $DRIFT_PERCENT -ge 0 ]; then
            DRIFT_TEXT=$(printf "LAG:  +%3d%%" "$DRIFT_PERCENT")
            DRIFT_COLOR="${ESC}[92m"
        else
            ABS_DRIFT=$(( -DRIFT_PERCENT ))
            DRIFT_TEXT=$(printf "LAG:  -%3d%%" "$ABS_DRIFT")
            if [ $DRIFT_PERCENT -ge -10 ]; then DRIFT_COLOR="${ESC}[93m"
            else DRIFT_COLOR="${ESC}[91m"; fi
        fi
        DRIFT_LEN=${#DRIFT_TEXT}
        echo "SPRITE,4,${DRIFT_LEN},1,${DRIFT_COLOR}${DRIFT_TEXT}${ESC}[0m"
        echo "DRAW,4,0,2,2,0"
        
        # Draw all fish (big=SPRITE 1, small=SPRITE 2)
        for ((i=0; i<FISH_COUNT; i++)); do
            if [ "${FTYPE[$i]}" -eq 0 ]; then
                # Big fish: redefine sprite 1 with this fish's color
                echo "SPRITE,1,6,3,${FCOLOR[$i]}>>AA<<${FCOLOR[$i]}>>BB<<${FCOLOR[$i]}>>CC<<"
                printf "DRAW,1,%d,%d,%d,0\n" "$((i+1))" "${FX[$i]}" "${FY[$i]}"
            else
                # Small fish: redefine sprite 2 with this fish's color
                echo "SPRITE,2,2,2,${FCOLOR[$i]}><${FCOLOR[$i]}><"
                printf "DRAW,2,%d,%d,%d,0\n" "$((i+1))" "${FX[$i]}" "${FY[$i]}"
            fi
        done
        
        # Draw all active bubbles (SPRITE 5)
        for ((i=0; i<MAX_BUBBLES; i++)); do
            if [ "${BACTIVE[$i]}" = "1" ]; then
                # Instance IDs for bubbles: 1000+i (to avoid fish instance collision)
                printf "DRAW,5,%d,%d,%d,0\n" "$((1000 + i))" "${BX[$i]}" "${BY[$i]}"
            fi
        done
        
        # Commit frame to terminal
        echo "FLUSH"
    } >&"${BRIDGE[1]}"
    
    # --- Update fish positions ---
    for ((i=0; i<FISH_COUNT; i++)); do
        FX[$i]=$(( ${FX[$i]} + ${FDX[$i]} ))
        FY[$i]=$(( ${FY[$i]} + ${FDY[$i]} ))
        if [ "${FX[$i]}" -le 1 ] || [ "${FX[$i]}" -ge $((COLS - 8)) ]; then
            FDX[$i]=$(( ${FDX[$i]} * -1 ))
        fi
        if [ "${FY[$i]}" -le 1 ] || [ "${FY[$i]}" -ge $((LINES - 5)) ]; then
            FDY[$i]=$(( ${FDY[$i]} * -1 ))
        fi
    done
    
    # --- Update bubbles (rise 1 row every 2 frames) ---
    if [ $((FRAME_COUNT % 2)) -eq 0 ]; then
        for ((i=0; i<MAX_BUBBLES; i++)); do
            if [ "${BACTIVE[$i]}" = "1" ]; then
                BY[$i]=$(( ${BY[$i]} - 1 ))
                if [ "${BY[$i]}" -lt 0 ]; then
                    BACTIVE[$i]=0
                fi
            fi
        done
    fi
    
    sleep 0.033
done

# Cleanup: close bridge stdin → Python gets EOF and exits cleanly
exec {BRIDGE[1]}>&-
