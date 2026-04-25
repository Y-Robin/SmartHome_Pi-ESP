(() => {
    const state = {
        sessions: [],
        activeSessionId: null,
        models: [],
    };

    const sessionList = document.getElementById('chat-session-list');
    const messagesContainer = document.getElementById('chat-messages');
    const titleEl = document.getElementById('active-chat-title');
    const modelLabelEl = document.getElementById('active-model-label');
    const statusEl = document.getElementById('ollama-status');
    const modelSelect = document.getElementById('model-select');
    const newChatBtn = document.getElementById('new-chat-btn');
    const chatForm = document.getElementById('chat-form');
    const chatInput = document.getElementById('chat-input');

    function escapeHtml(value) {
        return value
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#039;');
    }

    async function fetchJson(url, options = {}) {
        const response = await fetch(url, {
            headers: { 'Content-Type': 'application/json' },
            ...options,
        });
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.error || `Fehler ${response.status}`);
        }
        return payload;
    }

    function renderSessionList() {
        sessionList.innerHTML = '';
        if (!state.sessions.length) {
            sessionList.innerHTML = '<li class="snake-status">Noch keine Chats vorhanden.</li>';
            return;
        }
        for (const session of state.sessions) {
            const li = document.createElement('li');
            li.className = `ollama-session-item ${state.activeSessionId === session.id ? 'active' : ''}`;
            li.innerHTML = `<button type="button"><strong>${escapeHtml(session.title)}</strong><small>${escapeHtml(session.last_message_preview || 'Noch keine Nachrichten')}</small></button>`;
            li.querySelector('button').addEventListener('click', () => openSession(session.id));
            sessionList.appendChild(li);
        }
    }


    function upsertSession(session) {
        const index = state.sessions.findIndex((item) => item.id === session.id);
        if (index >= 0) {
            state.sessions[index] = session;
        } else {
            state.sessions.unshift(session);
        }
    }

    function appendMessage(role, content) {
        const row = document.createElement('div');
        row.className = `ollama-message ${role}`;
        row.innerHTML = `<p>${escapeHtml(content).replaceAll('\n', '<br>')}</p>`;
        messagesContainer.appendChild(row);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    async function loadModels() {
        const data = await fetchJson('/ollama-chat/api/models');
        state.models = data.models;
        modelSelect.innerHTML = '';
        for (const model of state.models) {
            const option = document.createElement('option');
            option.value = model;
            option.textContent = model;
            modelSelect.appendChild(option);
        }
        statusEl.textContent = state.models.length
            ? `${state.models.length} Modell(e) verfügbar`
            : 'Keine Modelle gefunden.';
    }

    async function loadSessions() {
        const data = await fetchJson('/ollama-chat/api/sessions');
        state.sessions = data.sessions;
        renderSessionList();

        if (!state.activeSessionId && state.sessions.length) {
            await openSession(state.sessions[0].id);
        }
    }

    async function createSession() {
        const model = modelSelect.value || '';
        const data = await fetchJson('/ollama-chat/api/sessions', {
            method: 'POST',
            body: JSON.stringify({ model }),
        });

        state.activeSessionId = data.session.id;
        upsertSession(data.session);
        renderSessionList();

        titleEl.textContent = data.session.title;
        modelLabelEl.textContent = data.session.model || modelSelect.value || '-';
        messagesContainer.innerHTML = '';
    }

    async function openSession(sessionId) {
        state.activeSessionId = sessionId;
        const data = await fetchJson(`/ollama-chat/api/sessions/${sessionId}/messages`);
        const session = data.session;

        titleEl.textContent = session.title;
        modelLabelEl.textContent = session.model || modelSelect.value || '-';

        messagesContainer.innerHTML = '';
        for (const message of data.messages) {
            appendMessage(message.role, message.content);
        }

        if (session.model && state.models.includes(session.model)) {
            modelSelect.value = session.model;
        }

        renderSessionList();
    }

    chatForm.addEventListener('submit', async (event) => {
        event.preventDefault();

        const prompt = chatInput.value.trim();
        if (!prompt) {
            return;
        }

        if (!state.activeSessionId) {
            await createSession();
        }

        chatInput.value = '';
        appendMessage('user', prompt);
        statusEl.textContent = 'Antwort wird generiert…';

        try {
            const data = await fetchJson('/ollama-chat/api/chat', {
                method: 'POST',
                body: JSON.stringify({
                    session_id: state.activeSessionId,
                    prompt,
                    model: modelSelect.value,
                }),
            });
            appendMessage('assistant', data.assistant_message.content);
            statusEl.textContent = 'Fertig.';
            titleEl.textContent = data.session.title;
            modelLabelEl.textContent = data.session.model || modelSelect.value || '-';
            upsertSession(data.session);
            renderSessionList();
        } catch (error) {
            appendMessage('assistant', `Fehler: ${error.message}`);
            statusEl.textContent = `Fehler: ${error.message}`;
        }
    });

    newChatBtn.addEventListener('click', async () => {
        try {
            await createSession();
        } catch (error) {
            statusEl.textContent = `Fehler: ${error.message}`;
        }
    });

    async function init() {
        try {
            await loadModels();
            await loadSessions();
        } catch (error) {
            statusEl.textContent = `Fehler beim Laden: ${error.message}`;
        }
    }

    init();
})();
