# Project Brain - Extensão VS Code

Extensão leve de sidebar de chat para o **Project Brain** (backend Python com bridge HTTP).

## Como instalar / compilar

Na pasta raiz da extensão (`project-brain-vscode/`):

```cmd
cd project-brain-vscode
npm.cmd install
npm.cmd run compile
```

## Como testar em modo debug (F5)

1. Abra a pasta `project-brain-vscode/` no VS Code.
2. Pressione **F5**. Uma nova janela do VS Code (Extension Development Host) abrirá.
3. Na nova janela, clique no ícone **Project Brain** na Activity Bar (barra lateral esquerda).
4. A sidebar de chat aparecerá. Se autoStart estiver ativo, o bridge Python será iniciado automaticamente.

## Como abrir a sidebar

- Clique no ícone **Project Brain** na Activity Bar, **ou**
- Abra a Command Palette (`Ctrl+Shift+P`) e execute `Project Brain: Open Chat`.

## Como configurar

Em **Settings > Extensions > Project Brain**:

| Configuração             | Padrão          | Descrição                                                  |
|--------------------------|-----------------|------------------------------------------------------------|
| `projectBrain.path`      | `../project-brain` | Caminho para a pasta do Project Brain (com `run_bridge.py`). |
| `projectBrain.pythonPath`| `python`        | Caminho para o executável Python.                          |
| `projectBrain.port`      | `8765`          | Porta do bridge HTTP do Project Brain.                     |
| `projectBrain.autoStart` | `true`          | Iniciar bridge automaticamente ao abrir a sidebar.         |
| `projectBrain.showTechnicalDetails` | `false` | Mostrar detalhes técnicos por padrão.              |

## Como empacotar (opcional)

Instale a ferramenta de empacotamento como devDependency e gere o `.vsix`:

```cmd
npm.cmd install --save-dev @vscode/vsce
npx vsce.cmd package
```

## Bridge HTTP (backend Python)

O backend do Project Brain fica em `../project-brain/` e expõe o bridge HTTP via `run_bridge.py` na porta configurada (padrão `8765`). A extensão se comunica via REST padrão (stdlib Node.js `http` — sem bibliotecas externas).

Principais comandos registrados:
- `Project Brain: Open Chat`
- `Project Brain: New Session`
- `Project Brain: Refresh Status`
- `Project Brain: Toggle Technical Details`

Logs do bridge estão no Output do VS Code, canal **Project Brain**.
