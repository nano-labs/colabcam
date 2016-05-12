# -​*- coding: utf-8 -*​-
u"""Funções para gerar movimentos de uma camera Pan-Tilt-Zoom."""

import StringIO
import sys
import serial
from redis import Redis
from flask import Flask, Blueprint, jsonify, request, render_template, send_file
import cv2
from PIL import Image
import numpy
cv = cv2.cv


DB = Redis(host="127.0.0.1", port=6379, db=0)

db_key = "camera"
db_frames = "camera-imagens"
DB.delete(db_key + "_x")
DB.delete(db_key + "_y")
DB.delete(db_key + "_z")

# Angulos máximos que a camera pode alcançar
LIMITS = (180, 180, 100)  # Pan (x), Tilt (y) e Zoom (z)

# Número de pedidos de posição a serem usados na média
MAX_SIZE = 1

try:
    SERIAL = serial.Serial('/dev/tty.usbserial-A900abSe', 9600, timeout=1)
    SERIAL.write('090090e')
except:
    print u"Não foi possivel abir Serial"
    SERIAL = open('lixo.txt', 'w')


class Camera:

    u"""Classe da câmera Pan Tilt Zoom."""

    @classmethod
    def axis_average(cls, axis, size):
        u"""Retorna a média de um unico eixo."""
        key = "%s_%s" % (db_key, axis)
        total_size = DB.llen(key)
        if total_size:
            items = DB.lrange(key, -size, -1)
            m = sum([int(i) for i in items]) / float(len(items))
            return int(m)
        return 0

    @classmethod
    def position(cls, size=MAX_SIZE):
        u"""Retorna o valor médio dos ultimo size itens."""
        return [cls.axis_average(i, size) for i in ("x", "y", "z")]

    @classmethod
    def axis_insert(cls, axis, value):
        u"""Insere um valor em um eixo."""
        key = "%s_%s" % (db_key, axis)
        DB.rpush(key, value)
        DB.ltrim(key, -MAX_SIZE, -1)

    @classmethod
    def insert(cls, x, y, z):
        u"""Insere uma posição na lista."""
        x = x if x >= 0 else 0
        x = x if x <= LIMITS[0] else LIMITS[0]
        y = y if y >= 0 else 0
        y = y if y <= LIMITS[1] else LIMITS[1]
        z = z if z >= 0 else 0
        z = z if z <= LIMITS[2] else LIMITS[2]
        cls.axis_insert("x", x)
        cls.axis_insert("y", y)
        cls.axis_insert("z", z)

    @classmethod
    def get_all(cls):
        """Retorna a lista inteira."""
        return zip(*[DB.lrange("%s_%s" % (db_key, i), 0, -1)
                     for i in ("x", "y", "z")])

    @classmethod
    def insert_differential(cls, x, y, z):
        u"""Insere um valor diferencial de posição."""
        X, Y, Z = cls.position()
        X += x
        Y += y
        Z += z
        cls.insert(X, Y, Z)

    @classmethod
    def goto(cls, x, y):
        u"""Move a câmera para a posição X, Y."""
        s = '%03d%03de' % (x, y)
        SERIAL.write(s)

    @classmethod
    def goto_average(cls):
        u"""Move a camera para a posição média."""
        x, y, z = cls.position()
        cls.goto(x, y)

app = Flask(__name__)
app.secret_key = 's3cr3t'

home = Blueprint('home', __name__)


@home.route('/', methods=['GET'])
def home_view():
    """Home."""
    x = request.args.get("x")
    y = request.args.get("y")
    z = request.args.get("z")
    if x and y and z:
        x, y, z = int(float(x)), int(float(y)), int(float(z))
        Camera.insert_differential(x, y, z)
        Camera.goto_average()
        X, Y, Z = Camera.position()
        return jsonify({"x": X, "y": Y, "z": Z})

    # Camera.goto_average()
    context = {}
    return render_template('home.html', **context), 200
    # return jsonify({}), 200


@home.route('/frame/<nome>', methods=['GET'])
def frame_maker(nome):
    """Retorna o frame mais recente."""
    from cStringIO import StringIO
    f = DB.lrange(db_frames, -2, -1)[0]
    dummy = StringIO
    imagem = Image.frombytes('RGB', (720, 480), f)
    arquivo = StringIO()
    imagem.save(arquivo, "png")
    arquivo.seek(0)
    response = send_file(arquivo, as_attachment=False, attachment_filename=nome)
    return response


app.register_blueprint(home)


@app.errorhandler(404)
def rotas(error):
    u"""Retorna o status 404 e alista das urls diponíveis."""
    urls = [["%s - %s" % (m, i.rule) for m in i.methods
             if m not in ("HEAD", "OPTIONS")]
            for i in app.url_map.iter_rules()]
    reposta = {'erro': 'url not found', 'status_code': 404,
               'urls_disponiveis': urls}
    return jsonify(reposta), 200


def capture():
    u"""Captura continuamente frames da camera e joga no redis."""
    vc = cv2.VideoCapture(0)
    if vc.isOpened():  # try to get the first frame
        rval, frame = vc.read()
    else:
        rval = False

    while rval:
        rval, frame = vc.read()
        frame = cv2.resize(frame, (720, 480))
        frame_string = frame.tostring()
        DB.rpush(db_frames, frame_string)
        DB.ltrim(db_frames, -10, -1)
        key = cv2.waitKey(20)
        if key == 27:  # exit on ESC
            break

if __name__ == '__main__':
    if len(sys.argv) == 1:
        Camera.insert(90, 90, 0)
        Camera.goto_average()
        app.use_reloader = True
        app.debug = True
        app.run(host="0.0.0.0", port=5000, threaded=True)
    else:
        capture()
