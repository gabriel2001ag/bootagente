# Memoria Operacional dos Subagentes

Registre somente fatos confirmados e reutilizaveis. Nao registre hipoteses,
segredos, dados de clientes ou logs extensos.

| Especialista | Area confirmada | Arquivos/fluxos conhecidos | Validacao | Atualizado em |
| --- | --- | --- | --- | --- |
| backend_ci4_audit | Pedido: rota `POST /pedido/nota` e emissao de nota | `Routes.php`, `Pedido::nota`, `PariPassuService::transmitirPedidoPariPassu` | Inspecao estatica | 2026-07-30 |
| mysql_schema |  |  |  |  |
| frontend_ui | Tela de pedidos integrada ao layout global | `pedido/pedido.php`, `layout/master.php`, Select2, DataTables e modais | Inspecao estatica | 2026-07-30 |
| qa_reviewer | Project Brain: filtros de indexacao, protecao sensivel, rebuild atomico e refresh de contexto | `project-brain/config.yaml`, scanner/indexer/search, auditoria de skips e Task 1 | Suite final `103 passed`; indice final `9378/5230/1409`; Task 1 `SENIOR_REQUIRED` | 2026-08-07 |
| docs_memory | Integracao externa do ERP com Project Brain, sem duplicacao no repositorio ERP | Checklist, decisao e retrospectiva desta etapa em `docs/agentes`; evidencia por item de conhecimento | Registro baseado no rebuild final, auditoria de skips, Git do ERP e handoff da Task 1 | 2026-08-07 |
| backend_ci4_audit | Project Brain V3: Chat sobre tasks, recuperação conceitual, confiança e Smart Router | `chat/`, `core/concepts.py`, `core/routing.py`, `core/context_compressor.py`, `core/orchestrator.py`, `senior/gateway.py` | `119 passed`; Task 3 `orders/0.73/ANALYSIS_ONLY`; Task 4 `business_flow/0.355/SENIOR` | 2026-08-07 |
| qa_reviewer | Regressão Task 1 -> Task 3 e fallback conservador | Task 3 reutilizou `3 rules/2 patterns/2 lessons/1 similar`; redução `11.11%` por caracteres | `119 passed`; ERP `OS-496` limpo no commit `280f3e9c...` | 2026-08-07 |
| docs_memory | Arquitetura e operação V3 documentadas | `project-brain/README.md`, `project-brain/V3_ARCHITECTURE.md`, checklist, decisão e retrospectiva V3 | Métricas comprovadas das Tasks 3/4 | 2026-08-07 |
| backend_ci4_audit | Pré-router conversacional do Chat com nove categorias e precedência técnica | `chat/classifier.py`, `chat/service.py`; casual/status/memória podem encerrar sem task | `132 passed`; `ola` com delta de task 0 e sem pipeline técnico | 2026-08-07 |
| qa_reviewer | Ausência de efeitos laterais em conversa casual e thresholds de recuperação | rule/pattern `0.20`, lesson/similar `0.10`, código `0.20`; fluxo de itens 3/2/2 `ANALYSIS_ONLY` | Baseline `119 passed`, final `132 passed`; ERP limpo | 2026-08-07 |
| docs_memory | Correção do pré-router documentada com limite conservador de paráfrases de status | README, arquitetura, checklist, decisão e retrospectiva específicos | Task 5 antes e `ola` depois registrados somente com fatos do QA | 2026-08-07 |
