from chat.sessions import ChatSessionRepository


def test_chat_history_is_separate_from_project_knowledge(db):
    from brain.projects import ProjectRepository

    project = ProjectRepository(db).get_or_create("/tmp/chat-project", name="chat-project")
    sessions = ChatSessionRepository(db)
    session = sessions.create(project.id)
    sessions.add_message(session.id, "user", "Analisar itens do pedido")
    sessions.add_message(session.id, "assistant", "Memória consultada")

    history = sessions.recent(session.id)
    assert [message.role for message in history] == ["user", "assistant"]
    assert db.query_one("SELECT COUNT(*) n FROM rules")["n"] == 0
    assert db.query_one("SELECT COUNT(*) n FROM lessons")["n"] == 0


def test_chat_session_offline_mode_and_close(db):
    from brain.projects import ProjectRepository

    project = ProjectRepository(db).get_or_create("/tmp/chat-project", name="chat-project")
    sessions = ChatSessionRepository(db)
    session = sessions.create(project.id)

    assert sessions.set_senior_mode(session.id, "offline").senior_mode == "OFFLINE"
    sessions.close(session.id)
    assert sessions.get(session.id).status == "CLOSED"

