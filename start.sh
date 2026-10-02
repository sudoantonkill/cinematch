#!/bin/bash

# Movie Recommendation System - Start Script

echo "Starting Movie Recommendation System..."

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Start Backend
echo "Starting Backend..."
cd "$SCRIPT_DIR/backend"
source venv/bin/activate
nohup python main.py > "$SCRIPT_DIR/backend.log" 2>&1 < /dev/null &
BACKEND_PID=$!
echo "Backend started with PID: $BACKEND_PID"

# Wait a moment for backend to initialize
sleep 3

# Start Frontend
echo "Starting Frontend..."
cd "$SCRIPT_DIR/frontend"
nohup npm run dev > "$SCRIPT_DIR/frontend.log" 2>&1 < /dev/null &
FRONTEND_PID=$!
echo "Frontend started with PID: $FRONTEND_PID"

# Save PIDs to file for stopping later
echo "$BACKEND_PID" > "$SCRIPT_DIR/.backend_pid"
echo "$FRONTEND_PID" > "$SCRIPT_DIR/.frontend_pid"

echo ""
echo "=========================================="
echo "✓ Services started successfully!"
echo "=========================================="
echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:5173 (or 5174 if 5173 is busy)"
echo ""
echo "Backend log: $SCRIPT_DIR/backend.log"
echo "Frontend log: $SCRIPT_DIR/frontend.log"
echo ""
echo "To stop all services, run: ./stop.sh"
echo "=========================================="
