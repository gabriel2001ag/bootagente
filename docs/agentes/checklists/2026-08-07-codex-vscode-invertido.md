# Checklist de Tarefa

## Identificacao

- Tarefa: ajustar o Project Brain para integração invertida com Codex no VS Code
- Data: 2026-08-07
- Status: concluido
- Agente coordenador: dev_senior

## Entendimento e decisoes

- Regra do usuario: não usar API, Codex CLI ou automação visual.
- Fato encontrado: extensão `openai.chatgpt` versão `26.5803.41515`.
- Fato encontrado: comandos públicos são de interface/contexto; não foi
  encontrada API pública de prompt/resposta no manifesto ou entrypoint.
- Decisão: Brain prepara contexto; Codex no VS Code consulta e submete resultado.
- MockSeniorProvider permanece apenas para testes síncronos.

## Plano executado

| Etapa | Responsavel | Status | Evidencia |
| --- | --- | --- | --- |
| Baseline V1 | qa_reviewer | concluido | 76 testes aprovados |
| Auditoria da extensão | backend_ci4_audit | concluido | manifesto e entrypoint inspecionados |
| Ponte invertida | dev_senior | concluido | pending/context/submit |
| Validação | qa_reviewer | concluido | 82 testes aprovados |
| Documentação | docs_memory | concluido | README e V2_ARCHITECTURE |

## Arquivos principais

- `project-brain/senior/codex_workspace_bridge.py`
- `project-brain/core/orchestrator.py`
- `project-brain/core/enums.py`
- `project-brain/core/config.py`
- `project-brain/cli/main.py`
- `project-brain/tests/test_codex_workspace_bridge.py`
- `project-brain/README.md`
- `project-brain/V2_ARCHITECTURE.md`

## Riscos e mitigacoes

- Extensão instalada não prova autenticação: status informa descoberta, não disponibilidade.
- Replay/concorrência: task é reservada com atualização condicional de estado.
- JSON inseguro: tipos, enums, confiança, booleanos e listas são validados antes de efeitos.
- Aprendizado indevido: exige aprovação explícita e respeita configuração global.
- Contexto obsoleto: commit Git é conferido; mudanças dirty sem novo commit ainda são limitação.
- Falha durante aprendizado: task muda para FAILED; atomicidade total do LearningExtractor
  ainda requer transação abrangente futura.

## Testes e evidencias

- V1 baseline: 76 aprovados.
- Resultado final: 82 aprovados.
- Fluxo integrado coberto: task -> handoff -> context -> submit -> learning.
- Cobertura adicional: JSON inválido, booleano textual, item de aprendizado inválido,
  replay e política de aprendizado desabilitada.
- `brain senior status`: extensão detectada sem invocação de UI/API/CLI Codex.

## Pendencias

- Detectar alteração dirty/untracked posterior à preparação, além do commit.
- Tornar sessão + aprendizado integralmente transacionais.
- Empacotar a ponte como MCP/skill oficial quando houver contrato estável.
- Executar demonstração manual em um projeto alvo Git registrado.

## Retrospectiva

- O que funcionou: investigar o mecanismo real evitou criar transporte não suportado.
- Padrao reaproveitavel: integrar ferramentas ao agente por pull/submit local validado.
- Nova regra: presença de extensão nunca equivale a API pública ou sessão disponível.
