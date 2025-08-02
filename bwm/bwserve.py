"""
Provide methods to manipulate Bitwarden vault using the Bitwarden CLI,
primarily via the `serve` command
"""
from http.client import HTTPConnection
import json
import logging
import subprocess
import socket
from urllib.parse import urlencode
from bwm.bwcli import Item


class BWHTTPConnection(HTTPConnection):
    """
    Open a stub HTTP Connection with our existing socket
    """
    def __init__(self, sock):
        super().__init__('bwserver', 80)
        self.sock = sock

    def connect(self):
        pass


class BWCLIServer:
    def __init__(self):
        self.client_sock, server_sock = socket.socketpair()
        self.process = subprocess.Popen(
            ["bw", "serve", "--hostname", f"fd+connected://{server_sock.fileno()}"],
            pass_fds=(server_sock.fileno(),)
        )

    def __del__(self):
        self.process.kill()
        self.process.wait()

    def get_status(self):
        successful, data = self.request('GET', '/status', None)
        successful = successful and data and 'template' in data
        return {'status': 'unauthenticated', 'serverUrl': None} if not successful else data['template']

    def unlock(self, passwd: str) -> tuple[str | bool, object]:
        successful, data = self.request('POST', '/unlock', {'password': passwd})
        if not successful:
            return False, "Failed to unlock"
        return data['raw'], ""

    def sync(self):
        successful, data = self.request('POST', '/sync')
        if not successful:
            logging.error(data['message'])
            return False
        return True

    def get_entries(self, org_name=''):
        successful, data = self.request('GET', '/list/object/items')
        if not successful:
            logging.error(data['message'])
            return False

        items = [Item(i) for i in data['data']]
        folders = self.get_folders()
        collections = self.get_collections(org_name)
        orgs = self.get_orgs()
        return items, folders, collections, orgs

    def get_folders(self):
        successful, data = self.request('GET', '/list/object/folders')
        if not successful:
            logging.error(data['message'])
            return False
        return {i['id']: i for i in data['data']}

    def get_collections(self, org_id=''):
        if org_id:
            successful, data = self.request('GET', '/list/object/org-collections', params={'organizationId', org_id})
        else:
            successful, data = self.request('GET', '/list/object/collections')
        if not successful:
            logging.error(data['message'])
            return False
        return {i['id']: i for i in data['data']}

    def get_orgs(self):
        successful, data = self.request('GET', '/list/object/organizations')
        if not successful:
            logging.error(data['message'])
            return False
        return {i['id']: i for i in data['data']}

    def request(self, method: str, url: str, body=None, params=None):
        conn = BWHTTPConnection(self.client_sock)
        encoded_body = None
        headers = {}
        if body:
            encoded_body = json.dumps(body).encode('utf-8')
            headers = {
                'Content-Type': 'application/json',
                'Content-Length': len(encoded_body)
            }
        if params:
            url = f'{url}?{urlencode(params)}'
        conn.request(method, url, encoded_body, headers)
        try:
            response = conn.getresponse()
            response_body = "\n".join([l.decode("utf-8") for l in response.readlines()])
            json_response = json.loads(response_body)
            return json_response['success'], json_response['data'] if json_response['success'] else json_response['message']
        except ConnectionResetError as e:
            return False, {}
