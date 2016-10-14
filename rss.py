import os
from datetime import datetime, timedelta
from flask import Flask, request, make_response, render_template
import hashlib
try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET
import requests
from functools import reduce
import configparser
import base64
app = Flask(__name__)

_RSS_CACHE = {}
_DOWNLOAD_RSS_CACHE = {}


config = configparser.RawConfigParser()
config.read(os.path.expanduser('~/.btpro/btpro.ini'))
_PASS_KEY_MD5 = config['Default']['pass_key_md5']


@app.route('/displayrss', methods=['GET'])
def pub_display():
    pass_key = request.args.get('passkey') or ''
    if _encrypt(pass_key) != _PASS_KEY_MD5:
        return 'not allowed', 401
    url = request.args.get('url')
    args = [(k, v) for k, v in request.args.items() if k not in ('url', 'passkey')]
    qs = reduce(lambda r, e: r + '{0}={1}&'.format(e[0], e[1]), args, '')[0:-1]
    url = '{0}?{1}'.format(url, qs)

    r = requests.get(url)
    response = make_response(_convert_rss(r.text))
    response.headers['content-type'] = r.headers['content-type']
    return response


def _convert_rss(rss):
    root = ET.fromstring(rss)
    for elem in root.iterfind('channel/item'):
        description_elem = list(elem.iter('description'))[0]
        description = description_elem.text
        guid = list(elem.iter(tag='guid'))[0].text
        if guid in _RSS_CACHE:
            description_elem.text = _RSS_CACHE[guid]
        else:
            title = list(elem.iter(tag='title'))[0].text
            t = list(elem.iter(tag='enclosure'))[0]
            torrent_url = t.attrib['url']
            torrent_length = t.attrib['length']
            qs = 'guid={0}&title={1}&url={2}&length={3}&passkey={4}'.format(guid, base64.urlsafe_b64encode(title.encode()).decode(), base64.urlsafe_b64encode(torrent_url.encode()).decode(), torrent_length, _PASS_KEY_MD5)
            description_elem.text = '<a href="addtodownload?' + qs + '">Download</a><br>' + description 

    return ET.tostring(root)


@app.route('/addtodownload', methods=['GET'])
def add_to_download():
    pass_key = request.args.get('passkey')
    if pass_key != _PASS_KEY_MD5:
        return 'Not allowed', 401
    guid = request.args.get('guid')
    if guid not in _DOWNLOAD_RSS_CACHE:
        title = base64.urlsafe_b64decode(request.args.get('title').encode()).decode()
        torrent_url = base64.urlsafe_b64decode(request.args.get('url').encode()).decode()
        torrent_length = request.args.get('length')
        _DOWNLOAD_RSS_CACHE[guid] = (title, torrent_url, torrent_length)

    return make_response()


@app.route('/downloadrss', methods=['GET'])
def pub_download():
    passkey = request.args.get('passkey')
    torrent_list = []
    for guid, val in _DOWNLOAD_RSS_CACHE.items():
        t = type('', (object,), {})
        t.guid = guid
        t.title = val[0]
        t.url = '{0}&passkey={1}'.format(val[1], passkey)
        t.length = val[2]
        torrent_list.append(t)
    response = make_response(render_template('rss_template.xml', torrent_list=torrent_list))
    response.headers['content-type'] = 'text/xml'
    return response


def _encrypt(s):
    m = hashlib.md5()
    m.update(s.encode())
    return m.hexdigest()


def _generate_pass_key():
    pass_key = base64.urlsafe_b64encode(os.urandom(16)).decode()
    _PASS_KEY = pass_key, datetime.now() + timedelta(hours=1)


_PASS_KEY = None
def _check_passkey(pass_key):
    if pass_key is None:
        return False
    if _PASS_KEY is None:
        return False
    if pass_key != _PASS_KEY[0]:
        return False
    if datetime.now() > _PASS_KEY[1]:
        return False




if __name__ == '__main__':
    app.run()