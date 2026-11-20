"""The SOMA skeleton and the small amount of 3D math the motion scripts share.

Plain Python, no numpy, so the same file runs under `python3` and inside
Blender. Quaternions are [x, y, z, w] (as MotionBricks and glTF write them),
the world is Y up and metres, and a character at heading 0 faces +Z with its
left side toward +X.

The skeleton itself (joint names, parents, rest pose) is read from
motion/soma_skeleton.json, which `just motion-skeleton` asks the worker for.
"""

from __future__ import annotations

import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SKELETON_FILE = os.path.join(REPO, "motion", "soma_skeleton.json")

X, Y, Z = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)
IDENTITY = (0.0, 0.0, 0.0, 1.0)


# ---- vectors -------------------------------------------------------------


def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def scale(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def length(a):
    return math.sqrt(dot(a, a))


def unit(a):
    n = length(a)
    if n < 1e-12:
        raise ValueError("cannot normalize a zero vector")
    return scale(a, 1.0 / n)


def lerp(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(len(a)))


def angle_between(a, b):
    """Degrees between two directions."""
    return math.degrees(math.acos(max(-1.0, min(1.0, dot(unit(a), unit(b))))))


# ---- quaternions [x, y, z, w] -------------------------------------------


def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def qconj(q):
    return (-q[0], -q[1], -q[2], q[3])


def qnorm(q):
    n = math.sqrt(sum(c * c for c in q))
    return tuple(c / n for c in q)


def qrot(q, v):
    """Rotate vector v by quaternion q."""
    u = (q[0], q[1], q[2])
    t = scale(cross(u, v), 2.0)
    return add(add(v, scale(t, q[3])), cross(u, t))


def qaxis(axis, degrees):
    half = math.radians(degrees) / 2.0
    s = math.sin(half)
    a = unit(axis)
    return (a[0] * s, a[1] * s, a[2] * s, math.cos(half))


def qangle(q):
    """How far a rotation turns, in degrees (0..180)."""
    return math.degrees(2.0 * math.acos(max(-1.0, min(1.0, abs(q[3])))))


def qslerp(a, b, t):
    d = sum(a[i] * b[i] for i in range(4))
    if d < 0.0:
        b, d = tuple(-c for c in b), -d
    if d > 0.9995:
        return qnorm(lerp(a, b, t))
    theta = math.acos(d)
    sa, sb = math.sin((1.0 - t) * theta), math.sin(t * theta)
    return qnorm(tuple((a[i] * sa + b[i] * sb) / math.sin(theta) for i in range(4)))


def qfrom_axes(x_axis, y_axis, z_axis):
    """The rotation whose matrix has these three unit columns."""
    m00, m10, m20 = x_axis
    m01, m11, m21 = y_axis
    m02, m12, m22 = z_axis
    trace = m00 + m11 + m22
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        q = ((m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s, 0.25 * s)
    elif m00 > m11 and m00 > m22:
        s = math.sqrt(1.0 + m00 - m11 - m22) * 2.0
        q = (0.25 * s, (m01 + m10) / s, (m02 + m20) / s, (m21 - m12) / s)
    elif m11 > m22:
        s = math.sqrt(1.0 + m11 - m00 - m22) * 2.0
        q = ((m01 + m10) / s, 0.25 * s, (m12 + m21) / s, (m02 - m20) / s)
    else:
        s = math.sqrt(1.0 + m22 - m00 - m11) * 2.0
        q = ((m02 + m20) / s, (m12 + m21) / s, 0.25 * s, (m10 - m01) / s)
    return qnorm(q)


def frame(direction, normal):
    """A rotation from two directions: `direction` exactly, `normal` as near as it can be."""
    d = unit(direction)
    n = unit(sub(normal, scale(d, dot(normal, d))))
    return qfrom_axes(d, n, cross(d, n))


def qfrom_to(d0, n0, d1, n1):
    """The rotation carrying direction d0 (with side n0) onto d1 (with side n1)."""
    return qmul(frame(d1, n1), qconj(frame(d0, n0)))


def yaw(degrees):
    """Turn about +Y. Heading 0 faces +Z; a positive heading turns toward +X (the character's left)."""
    return qaxis(Y, degrees)


def heading_of(q):
    """The heading, in degrees, that a rotation gives the +Z axis."""
    f = qrot(q, Z)
    return math.degrees(math.atan2(f[0], f[2]))


# ---- the skeleton ---------------------------------------------------------


class Skeleton:
    """The 30 joints MotionBricks animates, with their rest pose.

    rest_pos[i] and rest_rot[i] are joint i's transform in its parent;
    rest_world_rot[i] is its rotation in the world when nothing is bent.
    """

    def __init__(self, card: dict):
        index = {name: i for i, name in enumerate(card["joints"])}
        self.joints = list(card["model_joints"])
        self.index = {name: i for i, name in enumerate(self.joints)}
        self.parents = []
        self.rest_pos, self.rest_rot = [], []
        for name in self.joints:
            i = index[name]
            pos, rot = tuple(card["rest"][i][:3]), qnorm(tuple(card["rest"][i][3:7]))
            parent = card["parents"][i]
            # The file also lists finger joints the model leaves alone. A model
            # joint hanging off one (a fingertip) is re-hung on the nearest
            # model joint above it, keeping where it sits at rest.
            while parent >= 0 and card["joints"][parent] not in self.index:
                p_pos, p_rot = tuple(card["rest"][parent][:3]), qnorm(tuple(card["rest"][parent][3:7]))
                pos, rot = add(p_pos, qrot(p_rot, pos)), qmul(p_rot, rot)
                parent = card["parents"][parent]
            self.parents.append(-1 if parent < 0 else self.index[card["joints"][parent]])
            self.rest_pos.append(pos)
            self.rest_rot.append(qnorm(rot))
        self.children = [[c for c, p in enumerate(self.parents) if p == i] for i in range(len(self.joints))]
        self.rest_world_pos, self.rest_world_rot = self.fk(self.rest_pos[0], self.rest_rot)

    @classmethod
    def load(cls, path: str = SKELETON_FILE) -> "Skeleton":
        with open(path) as f:
            return cls(json.load(f))

    def fk(self, root, rotations):
        """World position and rotation of every joint, from the root position and local rotations."""
        pos, rot = [None] * len(self.joints), [None] * len(self.joints)
        for i, parent in enumerate(self.parents):
            if parent < 0:
                pos[i], rot[i] = tuple(root), qnorm(rotations[i])
            else:
                pos[i] = add(pos[parent], qrot(rot[parent], self.rest_pos[i]))
                rot[i] = qnorm(qmul(rot[parent], rotations[i]))
        return pos, rot

    def bone(self, parent: str, child: str) -> float:
        """Length of the bone from a joint to one of its children."""
        return length(self.rest_pos[self.index[child]])

    def rotation_list(self, rotations: dict):
        """Local rotations in joint order; joints not named keep their rest rotation."""
        out = list(self.rest_rot)
        for name, q in rotations.items():
            out[self.index[name]] = qnorm(tuple(q))
        return out
