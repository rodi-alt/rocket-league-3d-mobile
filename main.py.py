# main.py  -  CAR SOCCER 3D  (versione Kivy, pronta per Buildozer / Android)
# Prova prima sul PC:  pip install kivy   poi   python main.py
from kivy.config import Config
Config.set('kivy', 'exit_on_escape', '0')
Config.set('graphics', 'width', '1100'); Config.set('graphics', 'height', '620')
import math, random, os, wave, struct
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.core.audio import SoundLoader
from kivy.graphics import Color, Mesh, Line, Ellipse, Rectangle, Point
from kivy.metrics import sp
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label

W, L, GW, GH, CH = 25, 40, 7, 6, 22       # mezza larghezza, mezza lunghezza, porta, altezza porta, soffitto
GROUND, NEAR = 0.45, 0.5
CROWD_STEP = 2.2                           # distanza tra spettatori: alza il numero se il telefono scatta
BLUE, ORANGE = (.15, .55, 1.0), (1.0, .55, .1)
TEAMS = {'blu': BLUE, 'arancione': ORANGE}
FACES = (((0, 1, 3, 2), .75), ((4, 6, 7, 5), .75), ((2, 3, 7, 6), 1.0), ((0, 2, 6, 4), .55), ((1, 5, 7, 3), .85))


def opp(t): return 'arancione' if t == 'blu' else 'blu'
def clamp(v, a, b): return max(a, min(b, v))


def _ring(t, A, B):        # anello arrotondato attorno al campo (per gli spalti)
    c, s = math.cos(t), math.sin(t)
    return A * math.copysign(abs(c) ** (1 / 3), c), B * math.copysign(abs(s) ** (1 / 3), s)


# ---------------------------------------------------------------- SUONI (generati da codice)
SR = 16000


def _noise(n, a):
    y = 0; out = []
    for _ in range(n):
        y += a * (random.uniform(-1, 1) - y); out.append(y)
    return out


def _fade(x, n=800):
    for i in range(min(n, len(x) // 2)):
        x[i] *= i / n; x[-1 - i] *= i / n
    return x


def _engine(f0):
    tau = 2 * math.pi
    return [.3 * sum(math.sin(tau * f0 * k * t + k) / k for k in range(1, 6)) * (.85 + .15 * math.sin(tau * 6 * t))
            for t in (i / SR for i in range(SR))]


def _boost():
    n = SR; a = _noise(n, .3); b = _noise(n, .02)
    return _fade([a[i] * 2.2 + b[i] * 6 for i in range(n)])


def _bounce():
    out = []; ph = 0
    for i in range(int(.3 * SR)):
        t = i / SR; ph += 2 * math.pi * (55 + 120 * math.exp(-t * 18)) / SR
        out.append(math.sin(ph) * math.exp(-t * 13) * .9)
    return out


def _kick():
    n = int(.18 * SR); a = _noise(n, .5); out = []; ph = 0
    for i in range(n):
        t = i / SR; ph += 2 * math.pi * (70 + 200 * math.exp(-t * 40)) / SR
        out.append(a[i] * math.exp(-t * 35) * 1.6 + math.sin(ph) * math.exp(-t * 18) * .8)
    return out


def _crowd():
    n = 4 * SR; a = _noise(n, .25); b = _noise(n, .06)
    return _fade([(a[i] * .9 + b[i] * 2.5) * (.65 + .35 * math.sin(2 * math.pi * .5 * i / SR)) for i in range(n)])


def _cheer():
    n = int(3.5 * SR); a = _noise(n, .3); b = _noise(n, .03); out = []
    for i in range(n):
        t = i / SR
        out.append((a[i] * 1.2 - b[i] * 2) * min(t / .35, 1) * math.exp(-max(0, t - 1.4) * .9))
    for _ in range(150):
        p = random.randint(int(.2 * SR), int(3 * SR))
        amp = random.uniform(.3, .8) * math.exp(-max(0, p / SR - 1.6) * .7)
        for j in range(200):
            if p + j < n: out[p + j] += random.uniform(-1, 1) * math.exp(-j / 30) * amp
    return _fade(out)


def _whistle():
    n = int(.9 * SR); out = []; ph = 0
    for i in range(n):
        t = i / SR; ph += 2 * math.pi * (2900 + 150 * math.sin(2 * math.pi * 28 * t)) / SR
        out.append((math.sin(ph) * .5 + random.uniform(-1, 1) * .08) * min(t / .03, 1, (.9 - t) / .1))
    return out


def _jump():
    out = []; ph = 0
    for i in range(int(.18 * SR)):
        t = i / SR; ph += 2 * math.pi * (220 + 900 * t) / SR
        out.append(math.sin(ph) * math.exp(-t * 14) * .5)
    return out


SYNTH = {'eng_lo': lambda: _engine(60), 'eng_hi': lambda: _engine(110), 'boost': _boost, 'bounce': _bounce,
         'kick': _kick, 'crowd': _crowd, 'cheer': _cheer, 'whistle': _whistle, 'jump': _jump}
LOOPS = ('crowd', 'eng_lo', 'eng_hi', 'boost')


# ---------------------------------------------------------------- AUTO
class Car:
    def __init__(s, team, attack, hx, hz, bot, role):
        s.team, s.attack, s.bot, s.role, s.home, s.using = team, attack, bot, role, (hx, hz), False
        s.reset()

    def reset(s):
        s.x, s.y, s.z = s.home[0], GROUND, s.home[1]
        s.rot = 0 if s.attack == 1 else 180
        s.speed = s.yv = 0; s.boost = 100; s.jumps = 2; s.cv = (0, 0, 0)

    def fwd(s):
        r = math.radians(s.rot); return math.sin(r), math.cos(r)

    def jump(s):
        if s.jumps > 0:
            s.yv = 13; s.jumps -= 1; return True
        return False

    def drive(s, thr, steer, boost, dt):
        using = boost and s.boost > 0
        s.using = bool(using)
        if using: thr = 1; s.boost = max(0, s.boost - 33 * dt)
        else: s.boost = min(100, s.boost + 6 * dt)
        maxs = 32 if using else 18; acc = 50 if using else 26
        if thr: s.speed += thr * acc * dt
        else: s.speed -= s.speed * 2.5 * dt
        s.speed -= s.speed * .3 * dt
        s.speed = clamp(s.speed, -maxs * .6, maxs)
        s.rot += steer * 120 * dt * min(1, abs(s.speed) / 5) * (1 if s.speed >= 0 else -1)
        fx, fz = s.fwd()
        s.x += fx * s.speed * dt; s.z += fz * s.speed * dt
        s.yv -= 30 * dt; s.y += s.yv * dt
        if s.y <= GROUND: s.y = GROUND; s.yv = 0; s.jumps = 2
        s.x = clamp(s.x, -W + 2, W - 2); s.z = clamp(s.z, -L + 2, L - 2)
        s.cv = (fx * s.speed, s.yv, fz * s.speed)

    def think(s, g, dt):       # intelligenza artificiale dei bot
        bx, by, bz = g.b
        chase = s.role == 'att' or bz * s.attack < 5
        if chase:
            if s.z * s.attack > bz * s.attack - 1.5 and math.dist((s.x, s.z), (bx, bz)) > 4: tx, tz = bx, bz - s.attack * 9
            else: tx, tz = bx, bz
        else:
            tx, tz = bx * .5, -s.attack * L * .6 + bz * .2
        dx, dz = tx - s.x, tz - s.z
        diff = (math.degrees(math.atan2(dx, dz)) - s.rot + 180) % 360 - 180
        steer = clamp(diff / 25, -1, 1); dist = math.hypot(dx, dz)
        thr = .85 if abs(diff) < 110 else -.85
        if thr < 0: steer = -steer
        s.drive(thr, steer, chase and abs(diff) < 12 and dist > 18 and s.boost > 25, dt)
        if by > 2.5 and dist < 7 and random.random() < .05: s.jump()


# ---------------------------------------------------------------- GIOCO
class Game(FloatLayout):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.state = 'menu'; self.mode = 'pc'; self.team = 'blu'; self.ctrl = 'joystick'
        self.keys = set(); self.touch = {}; self.stick = (0, 0); self.ui = []; self.hud = {}; self.snd = {}
        self.cars = []; self.b = None; self.v = [0, 0, 0]; self.p = None
        self.cam = [0, 10, -30]; self.yaw = self.pitch = 0; self.orbit = 0; self.clock = 0
        self.over = self.freeze = self.ballcam = False
        self.build_world()
        Window.bind(on_key_down=self.kd, on_key_up=self.ku, on_keyboard=self.kb)
        Clock.schedule_interval(self.tick, 1 / 30)
        Clock.schedule_once(self.load_sounds, .4)
        self.title()

    # ---------- suoni
    def load_sounds(self, dt=0):
        try:
            folder = os.path.join(App.get_running_app().user_data_dir, 'sounds'); os.makedirs(folder, exist_ok=True)
            for name, fn in SYNTH.items():
                path = os.path.join(folder, name + '.wav')
                if not os.path.exists(path):
                    with wave.open(path, 'wb') as w:
                        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
                        w.writeframes(b''.join(struct.pack('<h', int(clamp(x, -1, 1) * 30000)) for x in fn()))
                self.snd[name] = SoundLoader.load(path)
        except Exception as e:
            print('Suoni non disponibili:', e)

    def sfx(self, name, vol=1.0):
        s = self.snd.get(name)
        if s: s.stop(); s.volume = vol; s.play()

    def start_sounds(self):
        for k in LOOPS:
            s = self.snd.get(k)
            if s: s.loop = True; s.volume = 0; s.play()
        self.sfx('whistle', .6)

    def stop_sounds(self):
        for k in LOOPS:
            s = self.snd.get(k)
            if s: s.stop()

    def update_audio(self):
        cel = self.freeze or self.over
        sp_ = 0 if cel else min(1, abs(self.p.speed) / 32)
        for k, v in (('crowd', .55 if cel else .3), ('eng_lo', .3 * (1 - sp_)), ('eng_hi', .3 * sp_),
                     ('boost', .5 if (self.p.using and not cel) else 0)):
            if self.snd.get(k): self.snd[k].volume = v

    # ---------- menu
    def clear_ui(self):
        for w in self.ui: self.remove_widget(w)
        self.ui = []

    def clear_hud(self):
        for w in self.hud.values(): self.remove_widget(w)
        self.hud = {}

    def label(self, text, y, size=40, col=(1, 1, 1, 1)):
        l = Label(text=text, font_size=sp(size), color=col, size_hint=(.8, .14), pos_hint={'center_x': .5, 'center_y': y})
        self.add_widget(l); self.ui.append(l)

    def btn(self, text, y, cb, col=(.2, .25, .4, 1)):
        b = Button(text=text, font_size=sp(22), size_hint=(.42, .12), pos_hint={'center_x': .5, 'center_y': y},
                   background_normal='', background_color=col)
        b.bind(on_release=lambda *_: cb()); self.add_widget(b); self.ui.append(b)

    def title(self):
        self.state = 'menu'; self.clear_ui(); self.clear_hud()
        self.label('CAR SOCCER 3D', .8, 54, (1, .9, .1, 1))
        self.btn('Gioca in modalità PC', .52, lambda: self.pick_team('pc'))
        self.btn('Gioca in modalità telefono', .36, lambda: self.pick_team('telefono'))

    def pick_team(self, mode):
        self.mode = mode; self.clear_ui()
        self.label('Scegli la squadra', .8, 40)
        self.btn('Squadra BLU', .55, lambda: self.chosen('blu'), BLUE + (1,))
        self.btn('Squadra ARANCIONE', .39, lambda: self.chosen('arancione'), ORANGE + (1,))

    def chosen(self, t):
        self.team = t
        if self.mode == 'pc': self.start()
        else:
            self.clear_ui(); self.label('Scegli i controlli', .8, 40)
            self.btn('Joystick', .55, lambda: self.set_ctrl('joystick'))
            self.btn('Freccette', .39, lambda: self.set_ctrl('freccette'))

    def set_ctrl(self, c):
        self.ctrl = c; self.start()

    # ---------- partita
    def start(self):
        self.clear_ui(); self.clear_hud(); self.build_world()
        self.score = {'blu': 0, 'arancione': 0}; self.time = 300.0
        self.over = self.freeze = self.ballcam = False; self.touch = {}; self.stick = (0, 0)
        me, ot = self.team, opp(self.team)
        self.cars = [Car(me, 1, 0, -20, False, 'att'), Car(me, 1, -9, -28, True, 'def'),
                     Car(ot, -1, 0, 20, True, 'att'), Car(ot, -1, 9, 28, True, 'def')]
        self.p = self.cars[0]; self.reset_all(); self.cam = [0, 5, -30]
        self.build_hud(); self.state = 'play'; self.start_sounds()

    def reset_all(self):
        for c in self.cars: c.reset()
        self.b = [0, 3, 0]; self.v = [0, 0, 0]

    def build_hud(self):
        for k, x, col, size in (('t', .5, (1, 1, 1, 1), 34), ('b', .39, BLUE + (1,), 46), ('o', .61, ORANGE + (1,), 46)):
            l = Label(text='', font_size=sp(size), color=col, size_hint=(.2, .12), pos_hint={'center_x': x, 'center_y': .93})
            self.add_widget(l); self.hud[k] = l
        m = Label(text='', font_size=sp(70), color=(1, .9, 0, 1), size_hint=(.8, .2), pos_hint={'center_x': .5, 'center_y': .62})
        self.add_widget(m); self.hud['m'] = m
        if self.mode == 'telefono':
            names = {'jump': 'SALTA', 'boost': 'BOOST', 'up': '^', 'down': 'v', 'left': '<', 'right': '>'}
            for n, (cx, cy, r) in self.zones().items():
                if n in names:
                    l = Label(text=names[n], font_size=sp(18), size_hint=(None, None), size=(2 * r, 2 * r))
                    l.center = (cx, cy); self.add_widget(l); self.hud['c' + n] = l

    def update_hud(self):
        t = math.ceil(self.time)
        self.hud['t'].text = f'{t // 60}:{t % 60:02d}'
        self.hud['b'].text = str(self.score['blu']); self.hud['o'].text = str(self.score['arancione'])

    def toggle_pause(self):
        if self.state == 'play' and not self.over:
            self.state = 'pause'
            for k in LOOPS:
                if self.snd.get(k): self.snd[k].volume = 0
            self.label('PAUSA', .75, 54)
            self.btn('Riprendi', .52, self.toggle_pause)
            self.btn('Esci dalla partita', .36, self.quit_match, (.5, .15, .15, 1))
        elif self.state == 'pause':
            self.clear_ui(); self.state = 'play'; self.touch = {}; self.stick = (0, 0)

    def quit_match(self):
        self.stop_sounds(); self.cars = []; self.b = None; self.title()

    def end_match(self):
        self.over = True; self.sfx('whistle', .8)
        a, b = self.score[self.team], self.score[opp(self.team)]
        self.hud['m'].text = 'HAI VINTO!' if a > b else 'HAI PERSO' if a < b else 'PAREGGIO'
        self.btn('Torna al menu', .3, self.quit_match)

    def goal(self, sz):
        scorer = self.team if sz > 0 else opp(self.team)
        self.score[scorer] += 1; self.freeze = True
        self.hud['m'].text = 'GOL!'; self.sfx('cheer', 1)
        Clock.schedule_once(self.after_goal, 2.5)

    def after_goal(self, dt):
        if not self.cars: return
        self.hud['m'].text = ''; self.reset_all(); self.freeze = False

    def do_jump(self):
        if self.state == 'play' and not (self.freeze or self.over) and self.p.jump(): self.sfx('jump', .5)

    # ---------- fisica palla
    def ball_physics(self, dt):
        b, v = self.b, self.v
        v[1] -= 22 * dt
        for i in range(3): b[i] += v[i] * dt
        v[0] *= 1 - .25 * dt; v[2] *= 1 - .25 * dt
        if b[1] < 1:
            if v[1] < -4: self.sfx('bounce', min(1, -v[1] / 18))
            b[1] = 1; v[1] = -v[1] * .72 if v[1] < -2 else 0
        if b[1] > CH - 1: b[1] = CH - 1; v[1] = -abs(v[1]) * .6
        if b[0] > W - 1.5:
            if v[0] > 6: self.sfx('bounce', min(.6, v[0] / 30))
            b[0] = W - 1.5; v[0] = -abs(v[0]) * .8
        if b[0] < -W + 1.5:
            if v[0] < -6: self.sfx('bounce', min(.6, -v[0] / 30))
            b[0] = -W + 1.5; v[0] = abs(v[0]) * .8
        if abs(b[2]) > L - 1:
            sz = 1 if b[2] > 0 else -1
            if abs(b[0]) < GW - 1 and b[1] < GH - 1:
                if abs(b[2]) > L + .5: self.goal(sz)
            else:
                b[2] = sz * (L - 1); v[2] = -sz * abs(v[2]) * .8
        sp_ = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
        if sp_ > 45:
            k = 45 / sp_; v[0] *= k; v[1] *= k; v[2] *= k

    def hit(self, c):
        b, v = self.b, self.v
        cx, cy, cz = c.x, c.y + .3, c.z
        nx, ny, nz = b[0] - cx, b[1] - cy, b[2] - cz
        d = math.sqrt(nx * nx + ny * ny + nz * nz)
        if .001 < d < 2.6:
            nx, ny, nz = nx / d, ny / d, nz / d
            b[0], b[1], b[2] = cx + nx * 2.6, cy + ny * 2.6, cz + nz * 2.6
            vn = (v[0] - c.cv[0]) * nx + (v[1] - c.cv[1]) * ny + (v[2] - c.cv[2]) * nz
            if vn < 0:
                if vn < -3: self.sfx('kick', min(1, -vn / 25))
                k = vn * 1.7
                v[0] += -nx * k + nx * 2; v[1] += -ny * k + ny * 2 + 1.5; v[2] += -nz * k + nz * 2

    # ---------- input
    def kd(self, win, key, *a):
        self.keys.add(key)
        if self.state == 'play' and not (self.over or self.freeze):
            if key == 32: self.do_jump()
            if key == 99: self.ballcam = not self.ballcam

    def ku(self, win, key, *a): self.keys.discard(key)

    def kb(self, win, key, *a):          # Esc / tasto indietro di Android = pausa
        if key == 27 and self.state in ('play', 'pause'):
            self.toggle_pause(); return True
        return False

    def zones(self):
        Wd, Ht = self.size; u = Ht / 10
        z = {'pause': (Wd - .8 * u, Ht - .8 * u, .7 * u)}
        if self.mode == 'telefono':
            z['jump'] = (Wd - 4.6 * u, 1.6 * u, 1.2 * u); z['boost'] = (Wd - 2.0 * u, 2.4 * u, 1.5 * u)
            if self.ctrl == 'joystick': z['stick'] = (2.6 * u, 2.6 * u, 2.0 * u)
            else: z.update(up=(2.6 * u, 4.1 * u, .8 * u), down=(2.6 * u, 1.1 * u, .8 * u),
                           left=(1.1 * u, 2.6 * u, .8 * u), right=(4.1 * u, 2.6 * u, .8 * u))
        return z

    def stick_update(self, t):
        cx, cy, r = self.zones()['stick']; R = self.height / 10 * 1.3
        dx, dy = t.x - cx, t.y - cy; d = math.hypot(dx, dy)
        if d > R: dx, dy = dx / d * R, dy / d * R
        self.stick = (dx / R, dy / R)          # (sterzo, acceleratore)

    def on_touch_down(self, t):
        if self.state != 'play' or self.over: return super().on_touch_down(t)
        for name, (cx, cy, r) in self.zones().items():
            if math.hypot(t.x - cx, t.y - cy) <= r:
                if name == 'pause': self.toggle_pause()
                elif name == 'jump': self.do_jump()
                else:
                    self.touch[t.uid] = name
                    if name == 'stick': self.stick_update(t)
                break
        return True

    def on_touch_move(self, t):
        if self.state != 'play': return super().on_touch_move(t)
        if self.touch.get(t.uid) == 'stick': self.stick_update(t)
        return True

    def on_touch_up(self, t):
        if self.state != 'play': return super().on_touch_up(t)
        if self.touch.pop(t.uid, None) == 'stick': self.stick = (0, 0)
        return True

    def inputs(self):
        k = self.keys
        thr = (119 in k or 273 in k) - (115 in k or 274 in k)
        steer = (100 in k or 275 in k) - (97 in k or 276 in k)
        boost = 304 in k or 303 in k
        if self.mode == 'telefono':
            roles = set(self.touch.values())
            if self.ctrl == 'joystick':
                if self.stick != (0, 0): steer, thr = self.stick
            else:
                thr = (('up' in roles) - ('down' in roles)) or thr
                steer = (('right' in roles) - ('left' in roles)) or steer
            boost = boost or 'boost' in roles
        return clamp(thr, -1, 1), clamp(steer, -1, 1), boost

    # ---------- telecamera
    def look(self, lx, ly, lz):
        dx, dy, dz = lx - self.cam[0], ly - self.cam[1], lz - self.cam[2]
        self.yaw = math.atan2(dx, dz); self.pitch = -math.atan2(dy, math.hypot(dx, dz))

    def follow(self, dt):
        p = self.p; bx, by, bz = self.b
        fx, fz = p.fwd()
        if self.ballcam:
            dx, dz = bx - p.x, bz - p.z; d = math.hypot(dx, dz)
            if d > .5: fx, fz = dx / d, dz / d
        c = self.cam; k = min(1, 6 * dt)
        c[0] += (p.x - fx * 10 - c[0]) * k; c[1] += (5 - c[1]) * k; c[2] += (p.z - fz * 10 - c[2]) * k
        c[0] = clamp(c[0], -W - 4, W + 4); c[2] = clamp(c[2], -L - 8, L + 8)
        if self.ballcam: self.look(bx, by, bz)
        else: self.look(p.x + fx * 8, 1, p.z + fz * 8)

    # ---------- ciclo principale
    def tick(self, dt):
        dt = min(dt, 1 / 20)
        if self.height < 10: return
        if self.state == 'menu':
            self.orbit += dt * .25; self.clock += dt
            self.cam = [22 * math.sin(self.orbit), 17, 40 * math.cos(self.orbit)]
            self.look(0, 2, 0); self.draw(); self.draw_ui(); return
        if self.state == 'pause':
            self.draw(); self.draw_ui(); return
        self.clock += dt
        if not (self.freeze or self.over):
            self.time = max(0, self.time - dt)
            thr, steer, boost = self.inputs()
            for c in self.cars:
                if c.bot: c.think(self, dt)
                else: c.drive(thr, steer, boost, dt)
            self.ball_physics(dt)
            for c in self.cars: self.hit(c)
            if self.time <= 0 and not self.freeze: self.end_match()
        self.follow(dt); self.update_hud(); self.update_audio(); self.draw(); self.draw_ui()

    # ---------- mondo statico: spalti e pubblico
    def build_world(self):
        mine, other = TEAMS[self.team], TEAMS[opp(self.team)]
        A0, B0, STEP, TIERS, SEG = W + 6, L + 14, 3.2, 4, 28
        hts = [1.2 + 2.2 * k for k in range(TIERS)]
        self.stands = []; self.crowd = []
        self.pal = [mine, other, (1, .1, .1), (1, 1, 1), (1, .9, 0), (.2, .9, .3)]
        for k in range(TIERS - 1, -1, -1):       # dai più lontani ai più vicini
            A, B, h = A0 + STEP * k, B0 + STEP * k, hts[k]
            for i in range(SEG):
                t1, t2 = 2 * math.pi * i / SEG, 2 * math.pi * (i + 1) / SEG
                a1, a2 = _ring(t1, A, B), _ring(t2, A, B)
                b1, b2 = _ring(t1, A + STEP, B + STEP), _ring(t2, A + STEP, B + STEP)
                g = .5 + .07 * (i % 2) - .08 * (k % 2)
                self.stands.append(([(a1[0], h, a1[1]), (a2[0], h, a2[1]), (b2[0], h, b2[1]), (b1[0], h, b1[1])], (g, g, g + .05)))
        for k in range(TIERS):
            A, B, h = A0 + STEP * k, B0 + STEP * k, hts[k]
            pts = [_ring(2 * math.pi * i / 600, A + 1.6, B + 1.6) for i in range(601)]
            acc = 0
            for j in range(1, 601):
                acc += math.dist(pts[j], pts[j - 1])
                if acc < CROWD_STEP: continue
                acc = 0; x, z = pts[j]
                if z < -L * .5 and random.random() < .6: ci = 0
                elif z > L * .5 and random.random() < .6: ci = 1
                else: ci = random.randrange(2, 6)
                self.crowd.append((x, h + .9, z, ci))

    # ---------- rendering 3D (proiezione fatta a mano)
    def tr(self, x, y, z):
        dx, dy, dz = x - self.cam[0], y - self.cam[1], z - self.cam[2]
        a, b, c, d, e, f, g, h = self.k
        return dx * a + dz * b, dx * c + dy * d + dz * e, dx * f + dy * g + dz * h

    def poly(self, pts, col, a=1):
        out = []; n = len(pts)
        for i in range(n):
            p, q = pts[i], pts[(i + 1) % n]
            ip, iq = p[2] > NEAR, q[2] > NEAR
            if ip: out.append(p)
            if ip != iq:
                t = (NEAR - p[2]) / (q[2] - p[2])
                out.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t, NEAR))
        if len(out) < 3: return
        v = []
        for x, y, z in out: v += (self.cx0 + x / z * self.F, self.cy0 + y / z * self.F, 0, 0)
        Color(col[0], col[1], col[2], a)
        Mesh(vertices=v, indices=list(range(len(out))), mode='triangle_fan')

    def wpoly(self, pts, col, a=1):
        cr = [self.tr(*p) for p in pts]
        if max(p[2] for p in cr) > NEAR: self.poly(cr, col, a)

    def seg(self, p, q, col, w=2, a=1):
        A, B = self.tr(*p), self.tr(*q)
        if A[2] <= NEAR and B[2] <= NEAR: return
        if A[2] <= NEAR:
            t = (NEAR - A[2]) / (B[2] - A[2]); A = (A[0] + (B[0] - A[0]) * t, A[1] + (B[1] - A[1]) * t, NEAR)
        elif B[2] <= NEAR:
            t = (NEAR - B[2]) / (A[2] - B[2]); B = (B[0] + (A[0] - B[0]) * t, B[1] + (A[1] - B[1]) * t, NEAR)
        Color(col[0], col[1], col[2], a)
        Line(points=[self.cx0 + A[0] / A[2] * self.F, self.cy0 + A[1] / A[2] * self.F,
                     self.cx0 + B[0] / B[2] * self.F, self.cy0 + B[1] / B[2] * self.F], width=w * self.height / 700)

    def box(self, items, c, off, size, col):
        r = math.radians(c.rot); s, co = math.sin(r), math.cos(r)
        sx, sy, sz = size; cr = []
        for dx in (-1, 1):
            for dy in (-1, 1):
                for dz in (-1, 1):
                    lx, ly, lz = off[0] + dx * sx / 2, off[1] + dy * sy / 2, off[2] + dz * sz / 2
                    cr.append(self.tr(c.x + lx * co + lz * s, c.y + ly, c.z - lx * s + lz * co))
        for q, sh in FACES:
            pts = [cr[i] for i in q]; zs = [p[2] for p in pts]
            if max(zs) > NEAR: items.append((sum(zs) / 4, pts, (col[0] * sh, col[1] * sh, col[2] * sh)))

    def draw(self):
        Wd, Ht = self.size
        self.F = Ht * .75; self.cx0, self.cy0 = Wd / 2, Ht / 2
        sy_, cy_, sp_, cp_ = math.sin(self.yaw), math.cos(self.yaw), math.sin(self.pitch), math.cos(self.pitch)
        self.k = (cy_, -sy_, sy_ * sp_, cp_, cy_ * sp_, sy_ * cp_, -sp_, cy_ * cp_)
        cb = self.canvas.before; cb.clear()
        with cb:
            Color(.45, .72, 1); Rectangle(pos=(0, 0), size=(Wd, Ht))
            hy = clamp(self.cy0 + math.tan(self.pitch) * self.F, 0, Ht)
            Color(.16, .18, .2); Rectangle(pos=(0, 0), size=(Wd, hy))
            self.draw_stands(); self.draw_field(); self.draw_objects()

    def draw_stands(self):
        for pts, col in self.stands:
            cr = [self.tr(*p) for p in pts]
            if max(p[2] for p in cr) > NEAR: self.poly(cr, col)
        cel = (self.freeze or self.over) and self.state != 'menu'
        bins = {}; s = self.height / 700
        for x, y, z, ci in self.crowd:
            jy = abs(math.sin(self.clock * 9 + ci)) * .5 if cel else 0
            xc, yc, zc = self.tr(x, y + jy, z)
            if zc <= NEAR: continue
            bn = 0 if zc < 35 else 1 if zc < 80 else 2
            bins.setdefault((ci, bn), []).extend((self.cx0 + xc / zc * self.F, self.cy0 + yc / zc * self.F))
        for (ci, bn), pts in bins.items():
            Color(*self.pal[ci]); Point(points=pts, pointsize=max(1.2, (4, 3, 2)[bn] * s))

    def draw_field(self):
        Lz = L + 6; n = 9
        for i in range(n):
            z0 = -Lz + i * 2 * Lz / n; z1 = z0 + 2 * Lz / n
            self.wpoly([(-W, 0, z0), (W, 0, z0), (W, 0, z1), (-W, 0, z1)], (.13, .5, .2) if i % 2 else (.17, .58, .25))
        wh = (1, 1, 1)
        self.wpoly([(-W, .02, -.15), (W, .02, -.15), (W, .02, .15), (-W, .02, .15)], wh, .8)
        for i in range(24):
            a1, a2 = 2 * math.pi * i / 24, 2 * math.pi * (i + 1) / 24
            self.seg((7 * math.cos(a1), .02, 7 * math.sin(a1)), (7 * math.cos(a2), .02, 7 * math.sin(a2)), wh, 2, .8)
        for x in (-W, W): self.seg((x, .02, -L), (x, .02, L), wh, 2, .8)
        for z in (-L, L): self.seg((-W, .02, z), (W, .02, z), wh, 2, .8)
        for sz, col in ((-1, TEAMS[self.team]), (1, TEAMS[opp(self.team)])):
            z = sz * L; zb = sz * (L + 6)
            self.wpoly([(-W, 0, z), (-GW, 0, z), (-GW, CH, z), (-W, CH, z)], col, .25)
            self.wpoly([(GW, 0, z), (W, 0, z), (W, CH, z), (GW, CH, z)], col, .25)
            self.wpoly([(-GW, GH, z), (GW, GH, z), (GW, CH, z), (-GW, CH, z)], col, .25)
            self.wpoly([(-GW, 0, zb), (GW, 0, zb), (GW, GH, zb), (-GW, GH, zb)], wh, .25)
            for sx in (-1, 1): self.wpoly([(sx * GW, 0, z), (sx * GW, 0, zb), (sx * GW, GH, zb), (sx * GW, GH, z)], wh, .18)
            for p, q in (((-GW, 0, z), (-GW, GH, z)), ((GW, 0, z), (GW, GH, z)), ((-GW, GH, z), (GW, GH, z))):
                self.seg(p, q, col, 5)
        for sx in (-1, 1): self.wpoly([(sx * W, 0, -L), (sx * W, 0, L), (sx * W, CH, L), (sx * W, CH, -L)], (.6, .9, 1), .10)

    def draw_objects(self):
        if not self.cars or not self.b: return
        bx, by, bz = self.b; items = []
        Color(0, 0, 0, .35)
        for x, z, r in [(c.x, c.z, 1.5) for c in self.cars] + [(bx, bz, max(.5, 1 - by * .04))]:
            xc, yc, zc = self.tr(x, .03, z)
            if zc > NEAR:
                w = 2 * r * self.F / zc
                Ellipse(pos=(self.cx0 + xc / zc * self.F - w / 2, self.cy0 + yc / zc * self.F - w * .15), size=(w, w * .3))
        for c in self.cars:
            col = TEAMS[c.team]
            self.box(items, c, (0, 0, 0), (1.8, .8, 2.8), col)
            self.box(items, c, (0, .6, -.28), (1.26, .64, 1.26), (.12, .12, .16))
            self.box(items, c, (0, .05, 1.43), (.8, .3, .12), (1, .9, .1))
        xc, yc, zc = self.tr(bx, by, bz)
        if zc > NEAR: items.append((zc, None, (self.cx0 + xc / zc * self.F, self.cy0 + yc / zc * self.F, max(3, self.F / zc))))
        items.sort(key=lambda it: -it[0])
        for d, pts, data in items:
            if pts is not None: self.poly(pts, data)
            else:
                sx, sy, r = data
                Color(.7, .7, .78); Ellipse(pos=(sx - r, sy - r), size=(2 * r, 2 * r))
                Color(1, 1, 1); Ellipse(pos=(sx - r * .9, sy - r * .7), size=(r * 1.5, r * 1.5))

    def draw_ui(self):           # pulsante pausa e controlli touch
        ca = self.canvas.after; ca.clear()
        if self.state != 'play' or self.over: return
        z = self.zones(); held = set(self.touch.values()); u = self.height / 10
        with ca:
            px, py, pr = z['pause']
            Color(1, 1, 1, .35); Ellipse(pos=(px - pr, py - pr), size=(2 * pr, 2 * pr))
            Color(0, 0, 0, .8)
            Rectangle(pos=(px - pr * .35, py - pr * .4), size=(pr * .2, pr * .8))
            Rectangle(pos=(px + pr * .15, py - pr * .4), size=(pr * .2, pr * .8))
            if self.mode != 'telefono': return
            for n, (cx, cy, r) in z.items():
                if n in ('pause', 'stick'): continue
                Color(1, 1, 1, .5 if n in held else .22); Ellipse(pos=(cx - r, cy - r), size=(2 * r, 2 * r))
            if 'stick' in z:
                cx, cy, r = z['stick']
                Color(1, 1, 1, .18); Ellipse(pos=(cx - 1.5 * u, cy - 1.5 * u), size=(3 * u, 3 * u))
                Color(1, 1, 1, .5); kx, ky = cx + self.stick[0] * 1.3 * u, cy + self.stick[1] * 1.3 * u
                Ellipse(pos=(kx - .6 * u, ky - .6 * u), size=(1.2 * u, 1.2 * u))


class CarSoccerApp(App):
    def build(self):
        self.title = 'Car Soccer 3D'
        self.game = Game()
        return self.game

    def on_pause(self):            # app in background su Android
        self.game.toggle_pause() if self.game.state == 'play' else None
        return True

    def on_resume(self): pass


if __name__ == '__main__':
    CarSoccerApp().run()
