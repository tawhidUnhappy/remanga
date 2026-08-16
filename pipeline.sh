#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ANSI color codes
CYAN='\033[1;36m'
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
MAGENTA='\033[1;35m'
RED='\033[1;31m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${CYAN}====================================================${NC}"
echo -e "${BOLD}${MAGENTA}       remanga - Guided Video Production Pipeline   ${NC}"
echo -e "${CYAN}====================================================${NC}"

# 1. Project Selection & Discovery
PROJECTS_DIR="projects"
mkdir -p "$PROJECTS_DIR"

existing_projects=()
for d in "$PROJECTS_DIR"/*; do
    if [ -d "$d" ]; then
        existing_projects+=("$(basename "$d")")
    fi
done

PROJECT_NAME=""
if [ ${#existing_projects[@]} -gt 0 ]; then
    echo -e "\n${YELLOW}Existing Projects Found:${NC}"
    for i in "${!existing_projects[@]}"; do
        pname="${existing_projects[$i]}"
        meta_file="$PROJECTS_DIR/$pname/project.json"
        saved_info=""
        if [ -f "$meta_file" ]; then
            saved_url=$(python3 -c "import json; print(json.load(open('$meta_file')).get('manga_url', ''))" 2>/dev/null || true)
            if [ -n "$saved_url" ]; then
                saved_info="[URL: $saved_url]"
            fi
        fi
        echo -e "  ${BOLD}[$((i+1))]${NC} $pname ${CYAN}$saved_info${NC}"
    done
    echo -e "  ${BOLD}[0]${NC} Create a new project"
    echo ""
    
    while [ -z "$PROJECT_NAME" ]; do
        read -e -r -p "$(echo -e "${BOLD}Select project number or type project name:${NC} ")" proj_choice
        if [[ "$proj_choice" =~ ^[0-9]+$ ]] && [ "$proj_choice" -ge 1 ] && [ "$proj_choice" -le "${#existing_projects[@]}" ]; then
            PROJECT_NAME="${existing_projects[$((proj_choice-1))]}"
        elif [ "$proj_choice" == "0" ]; then
            read -e -r -p "$(echo -e "${BOLD}Enter new project name:${NC} ")" new_name
            PROJECT_NAME="$(echo "$new_name" | tr ' ' '_')"
        elif [ -n "$proj_choice" ]; then
            PROJECT_NAME="$(echo "$proj_choice" | tr ' ' '_')"
        fi
    done
else
    while [ -z "$PROJECT_NAME" ]; do
        read -e -r -p "$(echo -e "${BOLD}Enter new project name (e.g. solo_leveling):${NC} ")" raw_name
        PROJECT_NAME="$(echo "$raw_name" | tr ' ' '_')"
    done
fi

echo -e "${GREEN}✓ Selected Project:${NC} ${BOLD}$PROJECT_NAME${NC}"

# 2. Manga URL / Identifier (with automatic reuse)
PROJECT_DIR="$PROJECTS_DIR/$PROJECT_NAME"
mkdir -p "$PROJECT_DIR"
META_FILE="$PROJECT_DIR/project.json"
SAVED_URL=""

if [ -f "$META_FILE" ]; then
    SAVED_URL=$(python3 -c "import json; print(json.load(open('$META_FILE')).get('manga_url', ''))" 2>/dev/null || true)
fi

MANGA_URL=""
if [ -n "$SAVED_URL" ]; then
    echo -e "\n${CYAN}Saved Manga Source:${NC} ${BOLD}$SAVED_URL${NC}"
    read -e -r -p "$(echo -e "${BOLD}Press Enter to reuse saved URL, or type a new URL:${NC} ")" input_url
    if [ -z "$input_url" ]; then
        MANGA_URL="$SAVED_URL"
    else
        MANGA_URL="$input_url"
    fi
else
    while [ -z "$MANGA_URL" ]; do
        read -e -r -p "$(echo -e "\n${BOLD}Enter MangaDex URL, UUID, or Manga Title:${NC} ")" MANGA_URL
    done
fi

# 3. Chapter Selection with Auto-Increment Suggestion
suggested_ch="1"
if [ -d "$PROJECT_DIR/chapters" ]; then
    highest_ch=0
    for ch_dir in "$PROJECT_DIR/chapters"/chapter_*; do
        if [ -d "$ch_dir" ]; then
            ch_basename="$(basename "$ch_dir")"
            ch_num="${ch_basename#chapter_}"
            if [[ "$ch_num" =~ ^[0-9]+$ ]] && [ "$ch_num" -gt "$highest_ch" ]; then
                highest_ch=$ch_num
            fi
        fi
    done
    if [ "$highest_ch" -gt 0 ]; then
        suggested_ch="$((highest_ch + 1))"
    fi
fi

read -e -r -p "$(echo -e "\n${BOLD}Enter Chapter Number [default: $suggested_ch]:${NC} ")" ch_input
CHAPTER="${ch_input:-$suggested_ch}"

CHAP_DIR="$PROJECT_DIR/chapters/chapter_$CHAPTER"
mkdir -p "$CHAP_DIR"

echo -e "\n${GREEN}====================================================${NC}"
echo -e "${BOLD}Starting Chapter Workflow: $PROJECT_NAME (Chapter $CHAPTER)${NC}"
echo -e "${GREEN}====================================================${NC}"

# Step 1: Download Pages
echo -e "\n${CYAN}[Step 1/6] Downloading Chapter Pages...${NC}"
./run.sh download --project "$PROJECT_NAME" --chapter "$CHAPTER" --url "$MANGA_URL"

# Step 2: Crops JSON Placement
CROPS_JSON="$CHAP_DIR/crops.json"
echo -e "\n${CYAN}[Step 2/6] LLM Panel Coordinate Crops${NC}"
if [ ! -f "$CROPS_JSON" ]; then
    echo -e "${YELLOW}Please generate 'crops.json' using 'prompts/crop_generation_prompt.md' and place it at:${NC}"
    echo -e "${BOLD}$CROPS_JSON${NC}"
    echo ""
    while [ ! -f "$CROPS_JSON" ]; do
        read -e -r -p "$(echo -e "${BOLD}Press Enter once 'crops.json' is saved at the above location...${NC} ")" _
        if [ ! -f "$CROPS_JSON" ]; then
            echo -e "${RED}File not found at $CROPS_JSON. Please ensure the file name and path are correct.${NC}"
        fi
    done
fi

# Step 3: Execute Cropping
echo -e "\n${CYAN}[Step 3/6] Cropping Panels from Coordinates...${NC}"
./run.sh crop --project "$PROJECT_NAME" --chapter "$CHAPTER"

# Step 4: Narration JSON Placement
NARRATION_JSON="$CHAP_DIR/narration.json"
echo -e "\n${CYAN}[Step 4/6] LLM Narration Script${NC}"
if [ ! -f "$NARRATION_JSON" ]; then
    echo -e "${YELLOW}Please generate 'narration.json' using 'prompts/narration_generation_prompt.md' and place it at:${NC}"
    echo -e "${BOLD}$NARRATION_JSON${NC}"
    echo ""
    while [ ! -f "$NARRATION_JSON" ]; do
        read -e -r -p "$(echo -e "${BOLD}Press Enter once 'narration.json' is saved at the above location...${NC} ")" _
        if [ ! -f "$NARRATION_JSON" ]; then
            echo -e "${RED}File not found at $NARRATION_JSON. Please ensure the file name and path are correct.${NC}"
        fi
    done
fi

# Step 5: Voice Generation & Mixing
echo -e "\n${CYAN}[Step 5/6] Synthesizing Narration Voice (en-US-GuyNeural)...${NC}"
./run.sh tts --project "$PROJECT_NAME" --chapter "$CHAPTER"

echo -e "\n${CYAN}Mixing Master Audio Stream & Normalizing Loudness...${NC}"
./run.sh mix --project "$PROJECT_NAME" --chapter "$CHAPTER"

# Step 6: Render Final Video
echo -e "\n${CYAN}[Step 6/6] Rendering Final Recap MP4 Video...${NC}"
./run.sh render --project "$PROJECT_NAME" --chapter "$CHAPTER"

# Display Status Summary
echo -e "\n${GREEN}====================================================${NC}"
echo -e "${BOLD}${GREEN}Production Complete!${NC}"
echo -e "${GREEN}====================================================${NC}"
./run.sh status --project "$PROJECT_NAME" --chapter "$CHAPTER"