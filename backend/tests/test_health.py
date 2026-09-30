from sqlalchemy.orm import sessionmaker

from app.db import get_db, make_engine


def test_health_ok_when_database_reachable(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_503_when_database_unreachable(app, client):
    # Nothing listens on port 1, so the connection is refused immediately.
    bad_engine = make_engine("postgresql+psycopg://x:x@127.0.0.1:1/x")
    BadSession = sessionmaker(bind=bad_engine)

    def broken_db():
        db = BadSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = broken_db
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
