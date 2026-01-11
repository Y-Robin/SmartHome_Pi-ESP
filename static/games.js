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
    const startButton = document.getElementById('snake-start');
    const resetButton = document.getElementById('snake-reset');
    const submitButton = document.getElementById('snake-submit');
    const submitStatus = document.getElementById('snake-submit-status');
    const playerInput = document.getElementById('snake-player');
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
        submitStatus.textContent = '';
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
        setStatus('Game Over! Trage deinen Namen ein und speichere den Score.');
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
    };

    const handleKeydown = (event) => {
        const key = event.key.toLowerCase();
        if (key === 'arrowup' || key === 'w') {
            applyDirection('up');
        } else if (key === 'arrowdown' || key === 's') {
            applyDirection('down');
        } else if (key === 'arrowleft' || key === 'a') {
            applyDirection('left');
        } else if (key === 'arrowright' || key === 'd') {
            applyDirection('right');
        }
    };

    const handleTouchInput = (event) => {
        event.preventDefault();
        const button = event.currentTarget;
        const directionValue = button.dataset.direction;
        if (directionValue) {
            applyDirection(directionValue);
        }
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

    const submitScore = async () => {
        submitStatus.textContent = '';
        const playerName = playerInput.value.trim();
        if (!playerName) {
            submitStatus.textContent = 'Bitte einen Namen eingeben.';
            return;
        }
        if (lastScore <= 0) {
            submitStatus.textContent = 'Erreiche zuerst einen Score > 0.';
            return;
        }

        try {
            const response = await fetch('/games/snake/score', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ name: playerName, score: lastScore }),
            });

            const payload = await response.json();
            if (!response.ok) {
                submitStatus.textContent = payload.error || 'Fehler beim Speichern.';
                return;
            }
            renderHighscores(payload.scores || []);
            submitStatus.textContent = 'Score gespeichert!';
            lastScore = 0;
        } catch (error) {
            submitStatus.textContent = 'Netzwerkfehler beim Speichern.';
        }
    };

    startButton.addEventListener('click', startGame);
    resetButton.addEventListener('click', resetGame);
    submitButton.addEventListener('click', submitScore);
    document.addEventListener('keydown', handleKeydown);
    document.querySelectorAll('.snake-touch-button').forEach(button => {
        button.addEventListener('touchstart', handleTouchInput, { passive: false });
        button.addEventListener('click', handleTouchInput);
    });

    resetGame();
})();
