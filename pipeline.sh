#!/usr/bin/env bash
set -euo pipefail

# ANSI Styling
BOLD='\033[1m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

echo -e "${BOLD}${CYAN}=====================================================${NC}"
echo -e "${BOLD}${CYAN}       remanga: Guided Manga Recap Production        ${NC}"
echo -e "${BOLD}${CYAN}=====================================================${NC}"

# 1. Project Details Input
read -rp "Enter Project / Manga Name: " PROJECT_NAME
read -rp "Enter MangaDex Title or URL/UUID: " MANGADEX_ID
read -rp "Enter Chapter Number (e.g. 1): " CHAPTER_NUM

CHAPTER_DIR="${SCRIPT_DIR}/projects/${PROJECT_NAME}/chapters/chapter_${CHAPTER_NUM}"

echo -e "\n${BOLD}${CYAN}==> [Step 1/4] Downloading Chapter Pages...${NC}"
./run.sh download --project "${PROJECT_NAME}" --url "${MANGADEX_ID}" --chapter "${CHAPTER_NUM}"

echo -e "\n${BOLD}${YELLOW}-----------------------------------------------------${NC}"
echo -e "${BOLD}${YELLOW}ACTION REQUIRED: Crop Coordinates (crops.json)${NC}"
echo -e "${YELLOW}1. Pages have been saved to:${NC}"
echo -e "   ${BOLD}${CHAPTER_DIR}/pages/${NC}"
echo -e "${YELLOW}2. Feed these pages along with ${CYAN}prompts/crop_generation_prompt.md${YELLOW} into your LLM.${NC}"
echo -e "${YELLOW}3. Save the returned JSON file to:${NC}"
echo -e "   ${BOLD}${GREEN}${CHAPTER_DIR}/crops.json${NC}"
echo -e "${BOLD}${YELLOW}-----------------------------------------------------${NC}"

while true; do
    read -rp "Have you placed 'crops.json' in the folder above? (y/n): " CONFIRM
    if [[ "$CONFIRM" =~ ^[Yy]$ ]]; then
        if [ -f "${CHAPTER_DIR}/crops.json" ]; then
            break
        else
            echo -e "${RED}File not found at: ${CHAPTER_DIR}/crops.json. Please check and retry.${NC}"
        fi
    fi
done

echo -e "\n${BOLD}${CYAN}==> [Step 2/4] Cropping Panels...${NC}"
./run.sh crop --project "${PROJECT_NAME}" --chapter "${CHAPTER_NUM}"

echo -e "\n${BOLD}${YELLOW}-----------------------------------------------------${NC}"
echo -e "${BOLD}${YELLOW}ACTION REQUIRED: Narration Script (narration.json)${NC}"
echo -e "${YELLOW}1. Cropped panels are ready at:${NC}"
echo -e "   ${BOLD}${CHAPTER_DIR}/panels/${NC}"
echo -e "${YELLOW}2. Feed the panels and previous memory along with ${CYAN}prompts/narration_generation_prompt.md${YELLOW} to your LLM.${NC}"
echo -e "${YELLOW}3. Save the returned narration JSON file to:${NC}"
echo -e "   ${BOLD}${GREEN}${CHAPTER_DIR}/narration.json${NC}"
echo -e "${BOLD}${YELLOW}-----------------------------------------------------${NC}"

while true; do
    read -rp "Have you placed 'narration.json' in the folder above? (y/n): " CONFIRM_NARR
    if [[ "$CONFIRM_NARR" =~ ^[Yy]$ ]]; then
        if [ -f "${CHAPTER_DIR}/narration.json" ]; then
            break
        else
            echo -e "${RED}File not found at: ${CHAPTER_DIR}/narration.json. Please check and retry.${NC}"
        fi
    fi
done

echo -e "\n${BOLD}${CYAN}==> [Step 3/4] Generating Voice Narration & Audio Mixing...${NC}"
./run.sh tts --project "${PROJECT_NAME}" --chapter "${CHAPTER_NUM}"
./run.sh mix --project "${PROJECT_NAME}" --chapter "${CHAPTER_NUM}"

echo -e "\n${BOLD}${CYAN}==> [Step 4/4] Rendering Final Recap MP4 Video...${NC}"
./run.sh render --project "${PROJECT_NAME}" --chapter "${CHAPTER_NUM}"

echo -e "\n${BOLD}${GREEN}=====================================================${NC}"
echo -e "${BOLD}${GREEN} ✓ Pipeline Completed Successfully!${NC}"
echo -e "${BOLD}${GREEN} Final Output: ${CHAPTER_DIR}/${PROJECT_NAME}_ch${CHAPTER_NUM}_recap.mp4${NC}"
echo -e "${BOLD}${GREEN}=====================================================${NC}"