import json
import os
from datetime import datetime

from net.http import RetryQueue


def test_retry_queue_file_ready_items(tmp_path):
    qfile = tmp_path / "retry_queue.json"
    rq = RetryQueue(queue_file=str(qfile))
    rq.add("http://example.com", headers={}, error="e")

    # Force next_retry to now for testing
    data = json.loads(qfile.read_text())
    assert len(data) == 1
    data[0]["next_retry"] = datetime.now().isoformat()
    qfile.write_text(json.dumps(data))

    ready = rq.get_ready_items(limit=10)
    assert len(ready) >= 1

