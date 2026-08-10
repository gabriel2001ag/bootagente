import * as vscode from 'vscode';
import * as http from 'http';
import * as child_process from 'child_process';
import * as path from 'path';
import * as fs from 'fs';

class BackendClient {
    private port: number;
    private baseUrl: string;
    private projectPath: string;
    private pythonPath: string;
    private autoStart: boolean;
    private process: child_process.ChildProcessWithoutNullStreams | null = null;
    private outputChannel: vscode.OutputChannel;

    constructor(
        port: number,
        projectPath: string,
        pythonPath: string,
        autoStart: boolean,
        outputChannel: vscode.OutputChannel
    ) {
        this.port = port;
        this.baseUrl = `http://127.0.0.1:${port}`;
        this.projectPath = projectPath;
        this.pythonPath = pythonPath;
        this.autoStart = autoStart;
        this.outputChannel = outputChannel;
    }

    updateConfig(port: number, projectPath: string, pythonPath: string, autoStart: boolean): void {
        this.port = port;
        this.baseUrl = `http://127.0.0.1:${port}`;
        this.projectPath = projectPath;
        this.pythonPath = pythonPath;
        this.autoStart = autoStart;
    }

    private request<T = any>(method: string, path: string, body?: any): Promise<T> {
        return new Promise((resolve, reject) => {
            const url = new URL(this.baseUrl + path);
            const options: http.RequestOptions = {
                hostname: url.hostname,
                port: url.port,
                path: url.pathname + url.search,
                method: method,
                timeout: 60000,
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                }
            };

            const req = http.request(options, (res) => {
                let data = '';
                res.on('data', (chunk) => { data += chunk; });
                res.on('end', () => {
                    try {
                        if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
                            if (data.trim() === '') {
                                resolve({} as T);
                            } else {
                                resolve(JSON.parse(data) as T);
                            }
                        } else {
                            let detail = '';
                            try {
                                const parsed = JSON.parse(data);
                                detail = parsed.error || parsed.message || data;
                            } catch {
                                detail = data;
                            }
                            reject({
                                message: `Erro ${res.statusCode} do Project Brain`,
                                detail: detail
                            });
                        }
                    } catch (e: any) {
                        reject({
                            message: 'Resposta inválida do Project Brain',
                            detail: e.message || String(e)
                        });
                    }
                });
            });

            req.on('error', (e: any) => {
                reject({
                    message: 'Não consegui acessar o Project Brain.',
                    detail: e.code === 'ECONNREFUSED'
                        ? 'Conexão recusada. Verifique se o bridge está rodando ou se a porta está correta.'
                        : (e.message || String(e))
                });
            });

            req.on('timeout', () => {
                req.destroy();
                reject({
                    message: 'Tempo esgotado ao acessar o Project Brain.',
                    detail: `Timeout após 60s em ${method} ${path}`
                });
            });

            if (body !== undefined) {
                req.write(JSON.stringify(body));
            }
            req.end();
        });
    }

    async isRunning(): Promise<boolean> {
        try {
            const result = await this.request<any>('GET', '/health');
            return result && result.ok === true;
        } catch {
            return false;
        }
    }

    async start(): Promise<void> {
        if (await this.isRunning()) {
            return;
        }
        if (!this.autoStart) {
            throw {
                message: 'Project Brain não está rodando e autoStart está desativado.',
                detail: 'Inicie manualmente ou ative projectBrain.autoStart.'
            };
        }

        if (this.process) {
            this.stop();
        }

        const cwd = path.isAbsolute(this.projectPath)
            ? this.projectPath
            : path.resolve(vscode.workspace.workspaceFolders?.[0]?.uri?.fsPath || process.cwd(), this.projectPath);

        if (!fs.existsSync(cwd)) {
            throw {
                message: 'Pasta do Project Brain não encontrada.',
                detail: `Caminho configurado: ${cwd}`
            };
        }

        const scriptPath = path.join(cwd, 'run_bridge.py');
        if (!fs.existsSync(scriptPath)) {
            throw {
                message: 'run_bridge.py não encontrado na pasta do Project Brain.',
                detail: `Esperado em: ${scriptPath}`
            };
        }

        const env: NodeJS.ProcessEnv = {
            ...process.env,
            PYTHONIOENCODING: 'utf-8',
            PYTHONUTF8: '1'
        };

        this.outputChannel.appendLine(`[Project Brain] Iniciando bridge na porta ${this.port}...`);
        this.outputChannel.appendLine(`[Project Brain] CWD: ${cwd}`);
        this.outputChannel.appendLine(`[Project Brain] Python: ${this.pythonPath}`);

        this.process = child_process.spawn(
            this.pythonPath,
            ['run_bridge.py', '--port', String(this.port)],
            {
                cwd: cwd,
                env: env,
                stdio: 'pipe'
            }
        );

        this.process.stdout.on('data', (data) => {
            this.outputChannel.append(`[Bridge stdout] ${data.toString('utf-8')}`);
        });

        this.process.stderr.on('data', (data) => {
            this.outputChannel.append(`[Bridge stderr] ${data.toString('utf-8')}`);
        });

        this.process.on('error', (err: any) => {
            this.outputChannel.appendLine(`[Bridge error] ${err.message || String(err)}`);
            this.process = null;
        });

        this.process.on('exit', (code, signal) => {
            this.outputChannel.appendLine(`[Bridge exit] code=${code} signal=${signal}`);
            this.process = null;
        });

        const maxWait = 10000;
        const step = 500;
        for (let waited = 0; waited < maxWait; waited += step) {
            await new Promise(r => setTimeout(r, step));
            if (await this.isRunning()) {
                this.outputChannel.appendLine(`[Project Brain] Bridge online na porta ${this.port}.`);
                return;
            }
        }

        throw {
            message: 'Project Brain não respondeu após inicialização.',
            detail: 'Verifique o Output "Project Brain" para mais detalhes.'
        };
    }

    stop(): void {
        if (this.process) {
            try {
                this.process.kill('SIGTERM');
            } catch {
                try { this.process.kill(); } catch {}
            }
            this.process = null;
        }
    }

    async getStatus(): Promise<any> {
        return this.request('GET', '/api/status');
    }

    async sendMessage(message: string, verbose?: boolean): Promise<any> {
        const body: any = { message };
        if (verbose !== undefined) { body.verbose = verbose; }
        return this.request('POST', '/api/chat', body);
    }

    async newSession(seniorMode?: 'ONLINE' | 'OFFLINE'): Promise<any> {
        const body: any = {};
        if (seniorMode !== undefined) { body.senior_mode = seniorMode; }
        return this.request('POST', '/api/session/new', body);
    }

    async setVerbose(on: boolean): Promise<any> {
        return this.request('POST', '/api/verbose', { on });
    }

    async setSeniorMode(mode: 'ONLINE' | 'OFFLINE'): Promise<any> {
        return this.request('POST', '/api/senior-mode', { mode });
    }

    async listTasks(limit?: number): Promise<any> {
        const q = limit !== undefined ? `?limit=${limit}` : '';
        return this.request('GET', `/api/tasks${q}`);
    }

    async searchMemory(query: string): Promise<any> {
        const q = encodeURIComponent(query);
        return this.request('GET', `/api/memory?query=${q}`);
    }

    async getHistory(limit?: number): Promise<any> {
        const q = limit !== undefined ? `?limit=${limit}` : '';
        return this.request('GET', `/api/session/history${q}`);
    }
}

class ChatSidebarProvider implements vscode.WebviewViewProvider {
    public static readonly viewType = 'projectBrain.chatView';
    private _view?: vscode.WebviewView;
    private client: BackendClient;
    private context: vscode.ExtensionContext;
    private lastStatus: any = null;

    constructor(client: BackendClient, context: vscode.ExtensionContext) {
        this.client = client;
        this.context = context;
    }

    public updateClient(client: BackendClient): void {
        this.client = client;
    }

    private getConfig() {
        return vscode.workspace.getConfiguration('projectBrain');
    }

    public async ensureStartedAndStatus(): Promise<any> {
        try {
            if (!(await this.client.isRunning())) {
                await this.client.start();
            }
            return await this.client.getStatus();
        } catch (e: any) {
            return { _error: e };
        }
    }

    public resolveWebviewView(
        webviewView: vscode.WebviewView,
        _context: vscode.WebviewViewResolveContext,
        _token: vscode.CancellationToken
    ): void {
        this._view = webviewView;

        const mediaDir = vscode.Uri.file(path.join(this.context.extensionPath, 'src', 'media'));
        const webview = webviewView.webview;

        webview.options = {
            enableScripts: true,
            localResourceRoots: [mediaDir]
        };

        webview.html = this.getHtml(webview, mediaDir);

        webview.onDidReceiveMessage(async (msg) => {
            await this.handleMessage(msg);
        });

        webviewView.onDidChangeVisibility(async () => {
            if (webviewView.visible) {
                await this.pushStatus();
            }
        });

        (async () => {
            await this.pushStatus();
        })();
    }

    private async pushStatus(): Promise<void> {
        if (!this._view) { return; }
        const status = await this.ensureStartedAndStatus();
        this.lastStatus = status;
        this._view.webview.postMessage({ type: 'statusUpdated', data: status });
        if (!status._error) {
            try {
                const history = await this.client.getHistory(100);
                this._view.webview.postMessage({ type: 'historyLoaded', data: history });
            } catch {}
        }
    }

    private async handleMessage(msg: any): Promise<void> {
        if (!this._view) { return; }
        const webview = this._view.webview;

        switch (msg.type) {
            case 'ready': {
                await this.pushStatus();
                const cfg = this.getConfig();
                webview.postMessage({
                    type: 'verboseChanged',
                    data: { on: !!cfg.get('showTechnicalDetails', false) }
                });
                break;
            }
            case 'refreshStatus': {
                await this.pushStatus();
                break;
            }
            case 'newSession': {
                try {
                    if (!(await this.client.isRunning())) { await this.client.start(); }
                    const result = await this.client.newSession();
                    webview.postMessage({ type: 'sessionChanged', data: result });
                    await this.pushStatus();
                } catch (e: any) {
                    webview.postMessage({ type: 'sessionChanged', data: { _error: e } });
                }
                break;
            }
            case 'toggleVerbose': {
                try {
                    if (!(await this.client.isRunning())) { await this.client.start(); }
                    const result = await this.client.setVerbose(!!msg.on);
                    webview.postMessage({ type: 'verboseChanged', data: result });
                } catch (e: any) {
                    webview.postMessage({ type: 'verboseChanged', data: { _error: e, on: !!msg.on } });
                }
                break;
            }
            case 'toggleSeniorMode': {
                try {
                    if (!(await this.client.isRunning())) { await this.client.start(); }
                    const result = await this.client.setSeniorMode(msg.mode);
                    webview.postMessage({ type: 'seniorChanged', data: result });
                    await this.pushStatus();
                } catch (e: any) {
                    webview.postMessage({ type: 'seniorChanged', data: { _error: e } });
                }
                break;
            }
            case 'loadHistory': {
                try {
                    if (!(await this.client.isRunning())) { await this.client.start(); }
                    const result = await this.client.getHistory(msg.limit || 100);
                    webview.postMessage({ type: 'historyLoaded', data: result });
                } catch (e: any) {
                    webview.postMessage({ type: 'historyLoaded', data: { _error: e } });
                }
                break;
            }
            case 'sendMessage': {
                const message = (msg.message || '').toString();
                if (!message.trim()) { return; }
                webview.postMessage({ type: 'processing', data: { on: true } });
                try {
                    if (!(await this.client.isRunning())) { await this.client.start(); }
                    const result = await this.client.sendMessage(message, msg.verbose);
                    webview.postMessage({
                        type: 'messageResponse',
                        data: {
                            message,
                            response: result
                        }
                    });
                } catch (e: any) {
                    webview.postMessage({
                        type: 'messageResponse',
                        data: {
                            message,
                            error: e
                        }
                    });
                } finally {
                    webview.postMessage({ type: 'processing', data: { on: false } });
                }
                break;
            }
        }
    }

    private getHtml(webview: vscode.Webview, mediaDir: vscode.Uri): string {
        const cssUri = webview.asWebviewUri(vscode.Uri.joinPath(mediaDir, 'sidebar.css'));
        const jsUri = webview.asWebviewUri(vscode.Uri.joinPath(mediaDir, 'sidebar.js'));
        const nonce = this.getNonce();

        return `<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="Content-Security-Policy"
          content="default-src 'none';
                   style-src ${webview.cspSource} 'nonce-${nonce}';
                   script-src 'nonce-${nonce}';
                   font-src ${webview.cspSource};">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="${cssUri}" rel="stylesheet" type="text/css">
    <title>Project Brain</title>
</head>
<body>
    <div class="app">
        <header class="bar header" id="headerBar">
            <div class="header-info">
                <span class="project" id="projectName">Projeto: --</span>
                <span class="branch" id="branchName">Branch: --</span>
                <span class="commit" id="commitHash">Commit: --</span>
            </div>
            <div class="header-actions">
                <span class="status-line">
                    <span class="status-dot" id="statusDot" title="Offline"></span>
                    <span class="status-text" id="statusText">Offline</span>
                </span>
                <button id="btnRefresh" title="Atualizar status">↻</button>
                <button id="btnNewSession" title="Nova sessão">Nova Sessão</button>
            </div>
        </header>

        <div class="messages" id="messages"></div>

        <div class="input-area">
            <textarea id="messageInput" rows="2" placeholder="Pergunte ao Project Brain... (Enter envia, Shift+Enter = nova linha)"></textarea>
            <div class="actions-row">
                <label class="toggle-switch">
                    <input type="checkbox" id="toggleVerbose">
                    <span>Detalhes técnicos</span>
                </label>
                <div class="send-row">
                    <button id="btnSend" disabled>Enviar ➤</button>
                </div>
            </div>
        </div>
    </div>

    <script nonce="${nonce}" src="${jsUri}"></script>
</body>
</html>`;
    }

    private getNonce(): string {
        let text = '';
        const possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
        for (let i = 0; i < 32; i++) {
            text += possible.charAt(Math.floor(Math.random() * possible.length));
        }
        return text;
    }
}

let client: BackendClient | null = null;
let provider: ChatSidebarProvider | null = null;
let outputChannel: vscode.OutputChannel | null = null;

function buildClientFromConfig(): BackendClient {
    const cfg = vscode.workspace.getConfiguration('projectBrain');
    const port = cfg.get('port', 8765);
    const projectPath = cfg.get('path', '../project-brain');
    const pythonPath = cfg.get('pythonPath', 'python');
    const autoStart = cfg.get('autoStart', true);
    if (!outputChannel) {
        outputChannel = vscode.window.createOutputChannel('Project Brain');
    }
    return new BackendClient(port, projectPath, pythonPath, autoStart, outputChannel);
}

export function activate(context: vscode.ExtensionContext): void {
    outputChannel = vscode.window.createOutputChannel('Project Brain');
    client = buildClientFromConfig();
    provider = new ChatSidebarProvider(client, context);

    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider(
            ChatSidebarProvider.viewType,
            provider,
            { webviewOptions: { retainContextWhenHidden: true } }
        )
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('projectBrain.openChat', async () => {
            await vscode.commands.executeCommand(
                'workbench.view.extension.projectBrain'
            );
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('projectBrain.newSession', async () => {
            try {
                if (client) {
                    if (!(await client.isRunning())) { await client.start(); }
                    await client.newSession();
                    vscode.window.showInformationMessage('Nova sessão do Project Brain iniciada.');
                }
            } catch (e: any) {
                vscode.window.showErrorMessage(`${e.message || 'Erro ao criar nova sessão'} Veja Output "Project Brain" para detalhes.`);
            }
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('projectBrain.refreshStatus', async () => {
            try {
                if (provider) {
                    await (provider as any).pushStatus?.();
                    vscode.window.showInformationMessage('Status do Project Brain atualizado.');
                }
            } catch (e: any) {
                vscode.window.showErrorMessage(e.message || 'Erro ao atualizar status.');
            }
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('projectBrain.toggleTechnical', () => {
            const cfg = vscode.workspace.getConfiguration('projectBrain');
            const current = cfg.get('showTechnicalDetails', false);
            cfg.update('showTechnicalDetails', !current, vscode.ConfigurationTarget.Global);
            vscode.window.showInformationMessage(`Detalhes técnicos: ${!current ? 'ON' : 'OFF'}`);
        })
    );

    context.subscriptions.push(
        vscode.workspace.onDidChangeConfiguration(async (e) => {
            if (e.affectsConfiguration('projectBrain')) {
                client = buildClientFromConfig();
                if (provider) {
                    provider.updateClient(client);
                    try { await (provider as any).pushStatus?.(); } catch {}
                }
            }
        })
    );

    context.subscriptions.push({
        dispose: () => {
            client?.stop();
            outputChannel?.dispose();
        }
    });
}

export function deactivate(): void {
    client?.stop();
    client = null;
    outputChannel?.dispose();
    outputChannel = null;
}
