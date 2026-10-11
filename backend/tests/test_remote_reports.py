from fastapi.testclient import TestClient


def test_report_lifecycle_and_admin_gate(tmp_path, monkeypatch):
    from lovktv import main
    from lovktv.storage import store
    monkeypatch.setattr(store, 'MEDIA_DIR', tmp_path / 'media')
    monkeypatch.setattr(store, 'DB_PATH', tmp_path / 'remote.sqlite')
    monkeypatch.setenv('LOVKTV_ADMIN_TOKEN', 'test-remote-admin')
    store.init_db()
    song = store.create_song('Owned recording', 'Me', 'en')
    with TestClient(main.app) as client:
        assert client.post('/api/remote/reports', json={'song_id': 'missing', 'reason': 'bad'}).status_code == 404
        assert client.post('/api/remote/reports', json={'song_id': song['id'], 'reason': ' '}).status_code == 422
        response = client.post('/api/remote/reports', json={'song_id': song['id'], 'reason': 'Copyright concern'})
        assert response.status_code == 201
        assert client.get('/api/admin/remote-reports').status_code == 401
        headers = {'Authorization': 'Bearer test-remote-admin'}
        reports = client.get('/api/admin/remote-reports', headers=headers).json()['reports']
        assert reports[0]['reason'] == 'Copyright concern'
        path = '/api/admin/remote-reports/' + response.json()['id']
        assert client.delete(path).status_code == 401
        assert client.delete(path, headers=headers).status_code == 200
        assert client.get('/api/admin/remote-reports', headers=headers).json()['reports'] == []
