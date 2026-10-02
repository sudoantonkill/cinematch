#!/bin/bash

# Movie Recommendation System - Stop Script

echo "Stopping Movie Recommendation System..."

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Check for PID files
BACKEND_PID_FILE="$SCRIPT_DIR/.backend_pid"
FRONTEND_PID_FILE="$SCRIPT_DIR/.frontend_pid"

# Stop Backend
if [ -f "$BACKEND_PID_FILE" ]; then
    BACKEND_PID=$(cat "$BACKEND_PID_FILE")
    if ps -p $BACKEND_PID > /dev/null 2>&1; then
        echo "Stopping Backend (PID: $BACKEND_PID)..."
        kill $BACKEND_PID
        rm "$BACKEND_PID_FILE"
        echo "✓ Backend stopped"
    else
        echo "Backend process not running"
        rm "$BACKEND_PID_FILE"
    fi
else
    echo "No backend PID file found"
fi

# Stop Frontend
if [ -f "$FRONTEND_PID_FILE" ]; then
    FRONTEND_PID=$(cat "$FRONTEND_PID_FILE")
    if ps -p $FRONTEND_PID > /dev/null 2>&1; then
        echo "Stopping Frontend (PID: $FRONTEND_PID)..."
        kill $FRONTEND_PID
        rm "$FRONTEND_PID_FILE"
        echo "✓ Frontend stopped"
    else
        echo "Frontend process not running"
        rm "$FRONTEND_PID_FILE"
    fi
else
    echo "No frontend PID file found"
fi

# Also kill any leftover processes on the ports
echo "Cleaning up any leftover processes..."
lsof -ti:8000 | xargs kill -9 2>/dev/null
lsof -ti:5173 | xargs kill -9 2>/dev/null

echo ""
echo "=========================================="
echo "✓ All services stopped!"
echo "=========================================="
