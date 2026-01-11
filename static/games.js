(() => {
    const canvas = document.getElementById('snake-canvas');
    if (!canvas) {
        return;
    }

    const tabs = document.querySelectorAll('.games-tab');
    const sections = document.querySelectorAll('.games-section');

    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const target = tab.dataset.game;
            tabs.forEach(button => button.classList.toggle('active', button === tab));
            sections.forEach(section => {
                section.classList.toggle('active', section.id === `${target}-section`);
            });
        });
    });

    const ctx = canvas.getContext('2d');
    const gridSize = 20;
    const tileCount = canvas.width / gridSize;

    const statusEl = document.getElementById('snake-status');
    const scoreEl = document.getElementById('snake-score');
    const highscoreList = document.getElementById('snake-highscore-list');

    let snake = [];
    let direction = { x: 1, y: 0 };
    let nextDirection = { x: 1, y: 0 };
    let food = { x: 10, y: 10 };
    let score = 0;
    let lastScore = 0;
    let intervalId = null;
    let isRunning = false;

    const updateScore = () => {
        scoreEl.textContent = score.toString();
    };

    const setStatus = (message) => {
        statusEl.textContent = message;
    };

    const drawTile = (x, y, color) => {
        ctx.fillStyle = color;
        ctx.fillRect(x * gridSize, y * gridSize, gridSize, gridSize);
        ctx.strokeStyle = '#ffffff';
        ctx.strokeRect(x * gridSize, y * gridSize, gridSize, gridSize);
    };

    const placeFood = () => {
        let newFood = null;
        while (!newFood) {
            const candidate = {
                x: Math.floor(Math.random() * tileCount),
                y: Math.floor(Math.random() * tileCount),
            };
            const hitSnake = snake.some(segment => segment.x === candidate.x && segment.y === candidate.y);
            if (!hitSnake) {
                newFood = candidate;
            }
        }
        food = newFood;
    };

    const resetGame = () => {
        snake = [
            { x: 7, y: 10 },
            { x: 6, y: 10 },
            { x: 5, y: 10 },
        ];
        direction = { x: 1, y: 0 };
        nextDirection = { x: 1, y: 0 };
        score = 0;
        lastScore = 0;
        updateScore();
        placeFood();
        setStatus('Bereit zum Spielen.');
        if (intervalId) {
            clearInterval(intervalId);
            intervalId = null;
        }
        isRunning = false;
        draw();
    };

    const resetAfterGameOver = () => {
        snake = [
            { x: 7, y: 10 },
            { x: 6, y: 10 },
            { x: 5, y: 10 },
        ];
        direction = { x: 1, y: 0 };
        nextDirection = { x: 1, y: 0 };
        placeFood();
        if (intervalId) {
            clearInterval(intervalId);
            intervalId = null;
        }
        isRunning = false;
        draw();
    };

    const draw = () => {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#e5e7eb';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        drawTile(food.x, food.y, '#f97316');
        snake.forEach((segment, index) => {
            drawTile(segment.x, segment.y, index === 0 ? '#0b6efd' : '#5a8dee');
        });
    };

    const gameStep = () => {
        direction = nextDirection;
        const head = { x: snake[0].x + direction.x, y: snake[0].y + direction.y };

        if (head.x < 0 || head.x >= tileCount || head.y < 0 || head.y >= tileCount) {
            endGame();
            return;
        }

        const hitSelf = snake.some(segment => segment.x === head.x && segment.y === head.y);
        if (hitSelf) {
            endGame();
            return;
        }

        snake.unshift(head);

        if (head.x === food.x && head.y === food.y) {
            score += 10;
            updateScore();
            placeFood();
        } else {
            snake.pop();
        }

        draw();
    };

    const startGame = () => {
        if (isRunning) {
            return;
        }
        isRunning = true;
        setStatus('Spiel läuft. Viel Erfolg!');
        intervalId = window.setInterval(gameStep, 140);
    };

    const endGame = () => {
        if (intervalId) {
            clearInterval(intervalId);
            intervalId = null;
        }
        isRunning = false;
        lastScore = score;
        score = 0;
        updateScore();
        resetAfterGameOver();
        setStatus('Game Over! Trage deinen Namen ein, um den Score zu speichern.');
        if (lastScore > 0) {
            const enteredName = window.prompt('Game Over! Bitte trage deinen Namen ein:', '');
            if (enteredName !== null) {
                const trimmedName = enteredName.trim();
                if (trimmedName) {
                    submitScore(trimmedName, lastScore);
                }
            }
        }
    };

    const applyDirection = (newDirection) => {
        const goingUp = direction.y === -1;
        const goingDown = direction.y === 1;
        const goingLeft = direction.x === -1;
        const goingRight = direction.x === 1;

        if (newDirection === 'up' && !goingDown) {
            nextDirection = { x: 0, y: -1 };
        } else if (newDirection === 'down' && !goingUp) {
            nextDirection = { x: 0, y: 1 };
        } else if (newDirection === 'left' && !goingRight) {
            nextDirection = { x: -1, y: 0 };
        } else if (newDirection === 'right' && !goingLeft) {
            nextDirection = { x: 1, y: 0 };
        }

        if (!isRunning) {
            startGame();
        }
    };

    const handleKeydown = (event) => {
        const key = event.key.toLowerCase();
        if (key === 'w') {
            applyDirection('up');
        } else if (key === 's') {
            applyDirection('down');
        } else if (key === 'a') {
            applyDirection('left');
        } else if (key === 'd') {
            applyDirection('right');
        }
    };

    const joystick = document.getElementById('snake-joystick');
    const joystickHandle = document.getElementById('snake-joystick-handle');
    const joystickState = {
        active: false,
        centerX: 0,
        centerY: 0,
        radius: 0,
    };

    const updateJoystick = (clientX, clientY) => {
        const dx = clientX - joystickState.centerX;
        const dy = clientY - joystickState.centerY;
        const distance = Math.hypot(dx, dy);
        const maxDistance = joystickState.radius;
        const limitedDistance = Math.min(distance, maxDistance);
        const angle = Math.atan2(dy, dx);
        const offsetX = Math.cos(angle) * limitedDistance;
        const offsetY = Math.sin(angle) * limitedDistance;
        joystickHandle.style.transform = `translate(${offsetX}px, ${offsetY}px)`;

        if (distance < maxDistance * 0.35) {
            return;
        }

        if (Math.abs(dx) > Math.abs(dy)) {
            applyDirection(dx > 0 ? 'right' : 'left');
        } else {
            applyDirection(dy > 0 ? 'down' : 'up');
        }
    };

    const resetJoystick = () => {
        joystickHandle.style.transform = 'translate(0, 0)';
    };

    const handleJoystickStart = (event) => {
        if (!joystick || !joystickHandle) {
            return;
        }
        joystickState.active = true;
        joystick.setPointerCapture(event.pointerId);
        const rect = joystick.getBoundingClientRect();
        joystickState.centerX = rect.left + rect.width / 2;
        joystickState.centerY = rect.top + rect.height / 2;
        joystickState.radius = rect.width / 2 - 12;
        updateJoystick(event.clientX, event.clientY);
    };

    const handleJoystickMove = (event) => {
        if (!joystickState.active) {
            return;
        }
        updateJoystick(event.clientX, event.clientY);
    };

    const handleJoystickEnd = () => {
        joystickState.active = false;
        resetJoystick();
    };

    const renderHighscores = (scores) => {
        highscoreList.innerHTML = '';
        if (!scores.length) {
            highscoreList.innerHTML = '<li>Noch keine Scores.</li>';
            return;
        }
        scores.forEach(scoreItem => {
            const li = document.createElement('li');
            li.innerHTML = `<strong>${scoreItem.name}</strong> – ${scoreItem.score}`;
            highscoreList.appendChild(li);
        });
    };

    const submitScore = async (playerName, scoreValue) => {
        try {
            const response = await fetch('/games/snake/score', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ name: playerName, score: scoreValue }),
            });

            const payload = await response.json();
            if (!response.ok) {
                setStatus(payload.error || 'Fehler beim Speichern.');
                return;
            }
            renderHighscores(payload.scores || []);
            lastScore = 0;
        } catch (error) {
            setStatus('Netzwerkfehler beim Speichern des Scores.');
        }
    };

    document.addEventListener('keydown', handleKeydown);
    if (joystick) {
        joystick.addEventListener('pointerdown', handleJoystickStart);
        joystick.addEventListener('pointermove', handleJoystickMove);
        joystick.addEventListener('pointerup', handleJoystickEnd);
        joystick.addEventListener('pointercancel', handleJoystickEnd);
        joystick.addEventListener('pointerleave', handleJoystickEnd);
    }

    resetGame();
})();
