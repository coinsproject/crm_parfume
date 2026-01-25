#!/bin/bash
# Скрипт для исправления структуры директорий
# Использование: ./fix_directory_structure.sh

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== Исправление структуры директорий ===${NC}"
echo ""

# Определяем текущую директорию
CURRENT_DIR=$(pwd)
echo -e "${YELLOW}Текущая директория: $CURRENT_DIR${NC}"
echo ""

# Проверяем структуру
echo -e "${YELLOW}Проверка структуры...${NC}"

# Проверяем, есть ли docker-compose.yml в текущей директории
if [ -f "docker-compose.yml" ]; then
    echo -e "${GREEN}✓ docker-compose.yml найден в текущей директории${NC}"
    CORRECT_DIR="$CURRENT_DIR"
elif [ -f "../docker-compose.yml" ]; then
    echo -e "${YELLOW}⚠ docker-compose.yml найден на уровень выше${NC}"
    CORRECT_DIR="$(cd .. && pwd)"
else
    echo -e "${RED}✗ docker-compose.yml не найден${NC}"
    echo -e "${YELLOW}Ищем docker-compose.yml...${NC}"
    FOUND=$(find /opt -maxdepth 3 -name "docker-compose.yml" 2>/dev/null | head -1)
    if [ -n "$FOUND" ]; then
        CORRECT_DIR=$(dirname "$FOUND")
        echo -e "${GREEN}✓ Найден в: $CORRECT_DIR${NC}"
    else
        echo -e "${RED}✗ docker-compose.yml не найден нигде!${NC}"
        exit 1
    fi
fi

echo ""
echo -e "${BLUE}Правильная директория: $CORRECT_DIR${NC}"
echo ""

# Проверяем, нужно ли что-то перемещать
if [ "$CURRENT_DIR" != "$CORRECT_DIR" ]; then
    echo -e "${YELLOW}Обнаружена неправильная структура директорий${NC}"
    echo -e "${YELLOW}Текущая: $CURRENT_DIR${NC}"
    echo -e "${YELLOW}Правильная: $CORRECT_DIR${NC}"
    echo ""
    
    # Проверяем, есть ли важные файлы в текущей директории
    IMPORTANT_FILES=("data/crm.db" "data" "logs" ".env")
    HAS_IMPORTANT=false
    
    for file in "${IMPORTANT_FILES[@]}"; do
        if [ -e "$file" ]; then
            HAS_IMPORTANT=true
            echo -e "${YELLOW}⚠ Найден важный файл/директория: $file${NC}"
        fi
    done
    
    if [ "$HAS_IMPORTANT" = true ]; then
        echo ""
        echo -e "${YELLOW}В текущей директории есть важные файлы (БД, логи, конфиги)${NC}"
        echo -e "${YELLOW}Нужно переместить их в правильную директорию${NC}"
        echo ""
        read -p "Переместить файлы в $CORRECT_DIR? (y/n): " -r
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo ""
            echo -e "${BLUE}Перемещение файлов...${NC}"
            
            # Переходим в правильную директорию
            cd "$CORRECT_DIR"
            
            # Перемещаем важные файлы
            if [ -d "$CURRENT_DIR/data" ]; then
                echo "Перемещение data/..."
                if [ -d "data" ]; then
                    echo -e "${YELLOW}Директория data уже существует, объединяем...${NC}"
                    cp -r "$CURRENT_DIR/data"/* data/ 2>/dev/null || true
                else
                    mv "$CURRENT_DIR/data" .
                fi
            fi
            
            if [ -d "$CURRENT_DIR/logs" ]; then
                echo "Перемещение logs/..."
                if [ -d "logs" ]; then
                    echo -e "${YELLOW}Директория logs уже существует, объединяем...${NC}"
                    cp -r "$CURRENT_DIR/logs"/* logs/ 2>/dev/null || true
                else
                    mv "$CURRENT_DIR/logs" .
                fi
            fi
            
            if [ -f "$CURRENT_DIR/.env" ]; then
                echo "Перемещение .env..."
                if [ -f ".env" ]; then
                    echo -e "${YELLOW}Файл .env уже существует, сохраняем старый как .env.old${NC}"
                    cp "$CURRENT_DIR/.env" ".env.old"
                else
                    mv "$CURRENT_DIR/.env" .
                fi
            fi
            
            echo -e "${GREEN}✓ Файлы перемещены${NC}"
        else
            echo -e "${YELLOW}Перемещение отменено${NC}"
        fi
    fi
    
    echo ""
    echo -e "${BLUE}Переход в правильную директорию: $CORRECT_DIR${NC}"
    cd "$CORRECT_DIR"
fi

# Проверяем финальную структуру
echo ""
echo -e "${BLUE}=== Финальная проверка структуры ===${NC}"
echo ""

REQUIRED_FILES=("docker-compose.yml" "Dockerfile" "update.sh")
ALL_OK=true

for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓ $file${NC}"
    else
        echo -e "${RED}✗ $file НЕ НАЙДЕН${NC}"
        ALL_OK=false
    fi
done

echo ""
if [ "$ALL_OK" = true ]; then
    echo -e "${GREEN}=== Структура директорий правильная! ===${NC}"
    echo ""
    echo -e "${BLUE}Текущая директория: $(pwd)${NC}"
    echo ""
    echo -e "${YELLOW}Теперь можно запустить обновление:${NC}"
    echo -e "  chmod +x update.sh"
    echo -e "  ./update.sh"
else
    echo -e "${RED}=== Есть проблемы со структурой ===${NC}"
    echo -e "${YELLOW}Проверьте, что все файлы на месте${NC}"
fi

# Предложение удалить лишнюю директорию
if [ "$CURRENT_DIR" != "$CORRECT_DIR" ] && [ -d "$CURRENT_DIR" ]; then
    echo ""
    echo -e "${YELLOW}Обнаружена лишняя директория: $CURRENT_DIR${NC}"
    
    # Проверяем, пустая ли она
    if [ -z "$(ls -A "$CURRENT_DIR" 2>/dev/null)" ]; then
        echo -e "${GREEN}Директория пустая, можно безопасно удалить${NC}"
        read -p "Удалить $CURRENT_DIR? (y/n): " -r
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rmdir "$CURRENT_DIR"
            echo -e "${GREEN}✓ Директория удалена${NC}"
        fi
    else
        echo -e "${YELLOW}В директории есть файлы. Проверьте содержимое:${NC}"
        ls -la "$CURRENT_DIR"
        echo ""
        read -p "Удалить директорию $CURRENT_DIR? (y/n): " -r
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo -e "${RED}ВНИМАНИЕ: Все файлы в директории будут удалены!${NC}"
            read -p "Вы уверены? (yes/no): " -r
            if [[ $REPLY == "yes" ]]; then
                rm -rf "$CURRENT_DIR"
                echo -e "${GREEN}✓ Директория удалена${NC}"
            else
                echo -e "${YELLOW}Удаление отменено${NC}"
            fi
        fi
    fi
fi

echo ""
echo -e "${GREEN}=== Готово ===${NC}"

