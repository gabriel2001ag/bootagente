# Registro de Decisao Tecnica

- Data: 2026-08-07
- Tarefa: filtros seguros de indexacao e refresh da Task 1
- Status: concluido
- Decisor: dev_senior

## Contexto

O indice externo do ERP continha diretorios gerados, dependencias e arquivos potencialmente sensiveis. O contexto da Task 1 havia sido produzido sobre esse indice ruidoso.

## Opcoes consideradas

1. Criar exclusoes fixas especificas para `infocase_web`.
2. Excluir `public` integralmente.
3. Centralizar defaults reutilizaveis, permitir `add`/`replace` por projeto, separar globs sensiveis e reconstruir o indice atomicamente.

## Decisao

Adotar a opcao 3. Scanner, indexador e busca usam a mesma politica normalizada para Windows. Globs sensiveis sao classificados como `SKIPPED_SENSITIVE` antes da leitura; a auditoria guarda somente caminho, classificacao e data. O rebuild troca o indice somente após sucesso e o refresh da Task 1 preserva revisoes anteriores.

Conhecimentos produzidos pelo Codex Senior devem trazer evidencia por item, com arquivos e simbolos quando aplicavel.

## Motivo

A solucao e reutilizavel por projeto, preserva arquivos validos em `public`, reduz risco de exposicao e impede inconsistencias entre indexacao e busca.

## Impacto

- Indice: `13810/5541/1951` para `9378/5230/1409`.
- Auditoria: `21802` skips, incluindo dois sensiveis sem conteudo.
- Task 1: `SENIOR_REQUIRED`, contexto de `2468` bytes, `15` candidatos e `2` revisoes.
- ERP: nenhum arquivo alterado pelo Project Brain.
- Risco conhecido: `PRE_EXISTING_CHANGE` em arquivo do ERP modificado localmente pelo usuario.

## Plano de reversao

Restaurar a configuracao/codigo anterior do Project Brain e reconstruir somente o indice do projeto 1. Tasks, rules, patterns, lessons e revisoes permanecem separados do conjunto substituivel do indice.
