from table_recognition_mineru.genie_model import MinerUTableModel as Model

if __name__ == "__main__":
    import sys

    task_id, token, url = sys.argv[1:]
    print(f"task_id: {task_id}, token: {token}, url: {url}")
    response_ = Model().execute_genie_v2(task_id=task_id, token=token, url=url)
    print(f"Status code: {response_.status_code}, content: {response_.content}")
