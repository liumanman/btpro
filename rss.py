import os
import json
from functools import reduce
from datetime import datetime, timedelta
from flask import Flask, request, make_response, render_template
import re
import hashlib
try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET
import requests
import configparser
import base64

app = Flask(__name__)

_RSS_CACHE = {}
_DOWNLOAD_RSS_CACHE = None 
_MAX_DOWNLOAD_RSS_COUNT = 3


config = configparser.RawConfigParser()
config.read(os.path.expanduser('~/.btpro/btpro.ini'))
_PASS_KEY_MD5 = config['Default']['pass_key_md5']

# _want_list = set([('the lunchbox', 'x264')])
_want_list = set()


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
    title_elem = list(root.iterfind('channel/title'))[0]
    title_elem.text += ' - btpro'
    link_elem = list(root.iterfind('channel/link'))[0]
    link_elem.text = 'https://kikk.ml/btpro'
    for elem in root.iterfind('channel/item'):
        description_elem = list(elem.iter('description'))[0]
        guid = list(elem.iter(tag='guid'))[0].text
        if guid in _RSS_CACHE:
            description_elem.text = _RSS_CACHE[guid]
        else:
            description = description_elem.text
            title = list(elem.iter(tag='title'))[0].text
            t = list(elem.iter(tag='enclosure'))[0]
            torrent_url = t.attrib['url']
            torrent_length = t.attrib['length']
            qs = 'guid={0}&title={1}&url={2}&length={3}&passkey={4}'.format(guid, base64.urlsafe_b64encode(title.encode()).decode(), base64.urlsafe_b64encode(torrent_url.encode()).decode(), torrent_length, _PASS_KEY_MD5)
            description += '<br><a href="https://kikk.ml/btpro/addtodownload?' + qs + '">Download</a><br>' #+ description 
            name = _get_name(title)
            if name:
                name_64 = base64.urlsafe_b64encode(name.encode()).decode()
                qs = 'title={0}&code=x265&passkey={1}'.format(name_64, _PASS_KEY_MD5)
                description += '<br><a href="https://kikk.ml/btpro/addtowant?' + qs + '">x265</a><br>' #+ description 
                qs = 'title={0}&code=x264&passkey={1}'.format(name_64, _PASS_KEY_MD5)
                description += '<br><a href="https://kikk.ml/btpro/addtowant?' + qs + '">x264</a><br>' #+ description 
                description_elem.text = description

            code = _get_code(title)
            name , code = name.lower(), code.lower() if code else None
            if (name, code) in _want_list:
                _add_to_download(guid, title, torrent_url, torrent_length)
                _want_list.remove((name, code))

            # _RSS_CACHE[guid] = description_elem.text
    return ET.tostring(root)


@app.route('/addtodownload', methods=['GET'])
def add_to_download():
    pass_key = request.args.get('passkey')
    if pass_key != _PASS_KEY_MD5:
        return 'Not allowed', 401

    guid = request.args.get('guid')
    title = base64.urlsafe_b64decode(request.args.get('title').encode()).decode()
    torrent_url = base64.urlsafe_b64decode(request.args.get('url').encode()).decode()
    torrent_length = request.args.get('length')
    _add_to_download(guid, title, torrent_url, torrent_length)
    return make_response('[{}] has been added to dowload rss.'.format(title))


def _add_to_download(guid, title, torrent_url, torrent_length):
    if _DOWNLOAD_RSS_CACHE is None:
        _load_download_rss()
    if guid not in _DOWNLOAD_RSS_CACHE:
        if len(_DOWNLOAD_RSS_CACHE) >= _MAX_DOWNLOAD_RSS_COUNT:
            t = reduce(lambda v, i: v if v[1][3] <= i[1][3] else i, _DOWNLOAD_RSS_CACHE.items())
            del _DOWNLOAD_RSS_CACHE[t[0]]

        in_date = datetime.now().strftime('%Y%m%d %H%M%S')
        _DOWNLOAD_RSS_CACHE[guid] = (title, torrent_url, torrent_length, in_date)
        _to_json_file(_DOWNLOAD_RSS_CACHE, 'download_rss.json')


@app.route('/downloadrss', methods=['GET'])
def pub_download():
    if _DOWNLOAD_RSS_CACHE is None:
        _load_download_rss()

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


@app.route('/addtowant', methods=['GET'])
def add_to_want():
    pass_key = request.args.get('passkey')
    if pass_key != _PASS_KEY_MD5:
        return 'Not allowed', 401

    code = request.args.get('code')
    title = base64.urlsafe_b64decode(request.args.get('title').encode()).decode()

    _want_list.add((title.lower(), code.lower()))
    return make_response('[{}] has been added to want list.'.format(title))


def _get_name(title):
    re_name = r'^\[.+\](.+) (?:20|19)\d\d'
    result = re.findall(re_name, title)
    return result[0] if len(result) > 0 else None


def _get_code(title):
    re_code = r'.+ (x264|x265)(?: |-).*HDS.*'
    result = re.findall(re_code, title)
    return result[0] if len(result) > 0 else None


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


def _to_json_file(o, file_name):
    file_path = os.path.join(os.path.dirname(__file__), file_name)    
    with open(file_path, 'w') as fd:
        json.dump(o, fd)


def _to_object(json_file_name):
    file_path = os.path.join(os.path.dirname(__file__), json_file_name)    
    if os.path.exists(file_path):
        with open(file_path) as fd:
            return json.load(fd)
    else:
        return {} 


def _load_download_rss():
    global _DOWNLOAD_RSS_CACHE
    _DOWNLOAD_RSS_CACHE = _to_object('download_rss.json')


if __name__ == '__main__':
    app.run()
