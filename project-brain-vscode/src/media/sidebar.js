(function () {
    'use strict';

    const vscode = acquireVsCodeApi();

    const state = {
        messages: [],
        technicalVisible: {},
        globalVerbose: false,
        processing: false,
        nextMsgId: 1
    };

    const els = {
        projectName: document.getElementById('projectName'),
        branchName: document.getElementById('branchName'),
        commitHash: document.getElementById('commitHash'),
        statusDot: document.getElementById('statusDot'),
        statusText: document.getElementById('statusText'),
        btnRefresh: document.getElementById('btnRefresh'),
        btnNewSession: document.getElementById('btnNewSession'),
        messages: document.getElementById('messages'),
        messageInput: document.getElementById('messageInput'),
        toggleVerbose: document.getElementById('toggleVerbose'),
        btnSend: document.getElementById('btnSend')
    };

    function setProcessing(processing) {
        state.processing = processing;
        els.btnSend.disabled = processing || !els.messageInput.value.trim();
        els.messageInput.disabled = processing;
        if (processing) {
            showLoadingIndicator();
        } else {
            hideLoadingIndicator();
        }
    }

    function showLoadingIndicator() {
        if (document.getElementById('loading-indicator')) { return; }
        const div = document.createElement('div');
        div.id = 'loading-indicator';
        div.className = 'loading-indicator';
        div.textContent = 'Brain está processando...';
        els.messages.appendChild(div);
        scrollToBottom();
    }

    function hideLoadingIndicator() {
        const el = document.getElementById('loading-indicator');
        if (el) { el.remove(); }
    }

    function scrollToBottom() {
        els.messages.scrollTop = els.messages.scrollHeight;
    }

    function createTechnicalBlock(technical, msgId) {
        const container = document.createElement('div');
        const toggleBtn = document.createElement('button');
        toggleBtn.className = 'technical-toggle';
        toggleBtn.textContent = '[ Ver detalhes ]';
        const details = document.createElement('div');
        details.className = 'technical-details';
        details.style.display = 'none';

        let text = '';
        if (typeof technical === 'string') {
            text = technical;
        } else if (technical !== null && technical !== undefined) {
            try {
                text = JSON.stringify(technical, null, 2);
            } catch {
                text = String(technical);
            }
        }
        details.textContent = text;

        toggleBtn.addEventListener('click', function () {
            if (details.style.display === 'none') {
                details.style.display = 'block';
                toggleBtn.textContent = '[ Ocultar ]';
                state.technicalVisible[msgId] = true;
            } else {
                details.style.display = 'none';
                toggleBtn.textContent = '[ Ver detalhes ]';
                state.technicalVisible[msgId] = false;
            }
        });

        if (state.technicalVisible[msgId] || state.globalVerbose) {
            details.style.display = 'block';
            toggleBtn.textContent = '[ Ocultar ]';
        }

        container.appendChild(toggleBtn);
        container.appendChild(details);
        return container;
    }

    function appendMessage(role, text, technical, providedMsgId) {
        const msgId = providedMsgId || ('msg-' + (state.nextMsgId++));
        const msgEl = document.createElement('div');
        msgEl.className = 'message ' + (role === 'user' ? 'user' : 'brain');
        msgEl.id = msgId;
        msgEl.dataset.role = role;

        const body = document.createElement('div');
        body.className = 'message-body';
        body.textContent = text || '';
        msgEl.appendChild(body);

        if (role === 'brain' && technical) {
            const techBlock = createTechnicalBlock(technical, msgId);
            msgEl.appendChild(techBlock);
        }

        els.messages.appendChild(msgEl);
        scrollToBottom();
        return msgId;
    }

    function appendErrorMessage(role, text, errorDetail) {
        const msgId = 'msg-' + (state.nextMsgId++);
        const msgEl = document.createElement('div');
        msgEl.className = 'message brain error-message';
        msgEl.id = msgId;

        const body = document.createElement('div');
        body.className = 'message-body';
        body.textContent = text || '';
        msgEl.appendChild(body);

        if (errorDetail) {
            const techBlock = createTechnicalBlock(errorDetail, msgId);
            msgEl.appendChild(techBlock);
        }

        els.messages.appendChild(msgEl);
        scrollToBottom();
        return msgId;
    }

    function clearMessages() {
        els.messages.innerHTML = '';
        state.technicalVisible = {};
    }

    function updateHeaderFromStatus(status) {
        if (!status) { return; }
        if (status._error) {
            if (els.projectName) { els.projectName.textContent = 'Projeto: --'; }
            if (els.branchName) { els.branchName.textContent = 'Branch: --'; }
            if (els.commitHash) { els.commitHash.textContent = 'Commit: --'; }
            setStatusDot(false);
            return;
        }
        if (status.project) {
            if (els.projectName) {
                els.projectName.textContent = 'Projeto: ' + (status.project.name || status.project.id || '--');
                els.projectName.title = 'Path: ' + (status.project.path || '');
            }
        }
        if (status.git) {
            if (els.branchName) {
                let branchText = 'Branch: ' + (status.git.branch || '--');
                if (status.git.dirty) { branchText += '*'; }
                els.branchName.textContent = branchText;
            }
            if (els.commitHash) {
                const commit = status.git.commit || '--';
                const shortCommit = commit.length > 8 ? commit.substring(0, 8) : commit;
                els.commitHash.textContent = 'Commit: ' + shortCommit;
                els.commitHash.title = commit;
            }
        }
        setStatusDot(true);
    }

    function setStatusDot(online) {
        if (!els.statusDot || !els.statusText) { return; }
        if (online) {
            els.statusDot.classList.add('online');
            els.statusDot.title = 'Online';
            els.statusText.textContent = 'Online';
        } else {
            els.statusDot.classList.remove('online');
            els.statusDot.title = 'Offline';
            els.statusText.textContent = 'Offline';
        }
    }

    function send() {
        if (state.processing) { return; }
        const message = (els.messageInput.value || '').toString();
        if (!message.trim()) { return; }
        vscode.postMessage({
            type: 'sendMessage',
            message: message,
            verbose: state.globalVerbose
        });
        els.messageInput.value = '';
        els.btnSend.disabled = true;
        setProcessing(true);
    }

    els.btnSend.addEventListener('click', send);

    els.messageInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            send();
        }
    });

    els.messageInput.addEventListener('input', function () {
        if (!state.processing) {
            els.btnSend.disabled = !els.messageInput.value.trim();
        }
    });

    els.btnRefresh.addEventListener('click', function () {
        vscode.postMessage({ type: 'refreshStatus' });
    });

    els.btnNewSession.addEventListener('click', function () {
        vscode.postMessage({ type: 'newSession' });
    });

    els.toggleVerbose.addEventListener('change', function () {
        state.globalVerbose = !!els.toggleVerbose.checked;
        vscode.postMessage({ type: 'toggleVerbose', on: state.globalVerbose });
    });

    window.addEventListener('message', function (event) {
        const msg = event.data || {};
        switch (msg.type) {
            case 'statusUpdated': {
                updateHeaderFromStatus(msg.data);
                if (msg.data && msg.data._error) {
                    const err = msg.data._error;
                    appendErrorMessage(
                        'brain',
                        err.message || 'Não consegui acessar o Project Brain.',
                        err.detail
                    );
                }
                break;
            }
            case 'verboseChanged': {
                if (msg.data && msg.data.on !== undefined) {
                    state.globalVerbose = !!msg.data.on;
                    els.toggleVerbose.checked = state.globalVerbose;
                }
                break;
            }
            case 'seniorChanged': {
                break;
            }
            case 'sessionChanged': {
                clearMessages();
                const notice = document.createElement('div');
                notice.className = 'loading-indicator';
                notice.style.fontStyle = 'normal';
                notice.textContent = 'Nova sessão iniciada.';
                els.messages.appendChild(notice);
                setTimeout(function () { notice.remove(); }, 2500);
                break;
            }
            case 'historyLoaded': {
                const data = msg.data;
                if (!data || !Array.isArray(data)) { break; }
                if (els.messages.children.length > 0) {
                    clearMessages();
                }
                for (let i = 0; i < data.length; i++) {
                    const item = data[i] || {};
                    const role = item.role === 'user' ? 'user' : 'brain';
                    appendMessage(role, item.message || '', null, item.id ? ('msg-hist-' + item.id) : undefined);
                }
                break;
            }
            case 'processing': {
                const on = !!(msg.data && msg.data.on);
                setProcessing(on);
                break;
            }
            case 'messageResponse': {
                setProcessing(false);
                const data = msg.data || {};
                const userText = data.message || '';
                appendMessage('user', userText);
                if (data.error) {
                    appendErrorMessage(
                        'brain',
                        data.error.message || 'Não consegui acessar o Project Brain.',
                        data.error.detail
                    );
                } else {
                    const resp = data.response || {};
                    const natural = resp.natural || resp.message || '';
                    const technical = resp.technical;
                    appendMessage('brain', natural, technical);
                }
                break;
            }
        }
    });

    vscode.postMessage({ type: 'ready' });
})();
