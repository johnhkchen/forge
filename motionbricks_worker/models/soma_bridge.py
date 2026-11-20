"""Carries poses between the two ways our motion models write the SOMA skeleton.

MotionBricks and the repo's motion format ("forge-soma-motion/1") write each
joint's rotation in its parent, where the T-pose is NOT all zeros: the
skeleton file gives every joint a rest rotation. Kimodo writes rotations so
that all zeros IS the T-pose, and its T-pose is a hair different (its shins
lean about five degrees, its hips sit 1 cm lower).

So a pose is carried across by what it looks like, not by its numbers: each
bone ends up pointing the same way in the world on both skeletons.

    world turn of joint j from the T-pose, Kimodo:  G[j]
    world rotation of joint j, MotionBricks:        W[j] = G[j] * C[j] * R[j]

R[j] is the joint's world rotation in MotionBricks' rest pose, and C[j] is the
small fixed turn that lays MotionBricks' rest bone along Kimodo's rest bone.

Plain Python, no numpy and no model code, so it runs the same in the worker
and in the repo's offline tests. Quaternions are [x, y, z, w]; Y is up.
"""

from __future__ import annotations

import math

# The bone each joint's direction is read from: the joint to this child.
# Joints not listed (hips, head, ends) carry no correction of their own.
MAIN_CHILD = {
    "Spine1": "Spine2",
    "Spine2": "Chest",
    "Chest": "Neck1",
    "Neck1": "Neck2",
    "Neck2": "Head",
    "LeftShoulder": "LeftArm",
    "LeftArm": "LeftForeArm",
    "LeftForeArm": "LeftHand",
    "LeftHand": "LeftHandMiddleEnd",
    "RightShoulder": "RightArm",
    "RightArm": "RightForeArm",
    "RightForeArm": "RightHand",
    "RightHand": "RightHandMiddleEnd",
    "LeftLeg": "LeftShin",
    "LeftShin": "LeftFoot",
    "LeftFoot": "LeftToeBase",
    "RightLeg": "RightShin",
    "RightShin": "RightFoot",
    "RightFoot": "RightToeBase",
}
# Leaves that follow their parent's correction, so a foot's toes stay in line with the foot.
FOLLOWS_PARENT = ("LeftToeBase", "RightToeBase", "LeftHandMiddleEnd", "RightHandMiddleEnd", "LeftHandThumbEnd", "RightHandThumbEnd")

IDENTITY = (0.0, 0.0, 0.0, 1.0)


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
    if n < 1e-12:
        raise ValueError("a rotation cannot be all zeros")
    return tuple(c / n for c in q)


def qrot(q, v):
    ux, uy, uz, w = q
    tx, ty, tz = 2.0 * (uy * v[2] - uz * v[1]), 2.0 * (uz * v[0] - ux * v[2]), 2.0 * (ux * v[1] - uy * v[0])
    return (v[0] + w * tx + uy * tz - uz * ty, v[1] + w * ty + uz * tx - ux * tz, v[2] + w * tz + ux * ty - uy * tx)


def qyaw(degrees):
    half = math.radians(degrees) / 2.0
    return (0.0, math.sin(half), 0.0, math.cos(half))


def qbetween(a, b):
    """The shortest turn that carries direction a onto direction b."""
    la, lb = math.sqrt(sum(c * c for c in a)), math.sqrt(sum(c * c for c in b))
    if la < 1e-9 or lb < 1e-9:
        return IDENTITY
    a, b = [c / la for c in a], [c / lb for c in b]
    d = a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
    if d < -0.999999:
        raise ValueError("the two rest poses point a bone in opposite directions")
    cross = (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
    return qnorm((cross[0], cross[1], cross[2], 1.0 + d))


def to_axis_angle(q):
    """A rotation as axis times angle (radians), the way Kimodo's constraint files write one."""
    q = qnorm(q)
    if q[3] < 0.0:
        q = tuple(-c for c in q)
    s = math.sqrt(max(0.0, 1.0 - q[3] * q[3]))
    if s < 1e-9:
        return [2.0 * q[0], 2.0 * q[1], 2.0 * q[2]]
    angle = 2.0 * math.atan2(s, q[3])
    return [q[0] / s * angle, q[1] / s * angle, q[2] / s * angle]


class Bridge:
    """Built once from the two rest poses; carries poses both ways.

    card          the skeleton card MotionBricks answers `skeleton` with (and
                  motion/soma_skeleton.json): joints, parents, rest, model_joints
    kimodo_rest   {joint name: [x, y, z]} of Kimodo's T-pose, any origin
    kimodo_hips_y how high Kimodo's hips are above the ground in its T-pose
    """

    def __init__(self, card: dict, kimodo_rest: dict, kimodo_hips_y: float = 1.0):
        index = {name: i for i, name in enumerate(card["joints"])}
        self.joints = list(card["model_joints"])
        self.index = {name: i for i, name in enumerate(self.joints)}
        missing = [name for name in self.joints if name not in kimodo_rest]
        if missing:
            raise ValueError(f"Kimodo's skeleton lacks {', '.join(missing)}")
        self.parents, self.rest_pos, self.rest_rot = [], [], []
        for name in self.joints:
            i = index[name]
            pos, rot = tuple(card["rest"][i][:3]), qnorm(tuple(card["rest"][i][3:7]))
            parent = card["parents"][i]
            # A model joint hanging off a finger joint the models leave alone is
            # re-hung on the nearest model joint above it (as scripts/motion/soma.py does).
            while parent >= 0 and card["joints"][parent] not in self.index:
                p_pos, p_rot = tuple(card["rest"][parent][:3]), qnorm(tuple(card["rest"][parent][3:7]))
                pos = tuple(p_pos[a] + qrot(p_rot, pos)[a] for a in range(3))
                rot = qmul(p_rot, rot)
                parent = card["parents"][parent]
            self.parents.append(-1 if parent < 0 else self.index[card["joints"][parent]])
            self.rest_pos.append(pos)
            self.rest_rot.append(qnorm(rot))
        world_pos, self.rest_world = self.fk(self.rest_pos[0], self.rest_rot)
        # The fixed turn per joint that lays our rest bone along Kimodo's.
        self.fix = [IDENTITY] * len(self.joints)
        for j, name in enumerate(self.joints):
            child = MAIN_CHILD.get(name)
            if child is None:
                continue
            c = self.index[child]
            ours = tuple(world_pos[c][a] - world_pos[j][a] for a in range(3))
            theirs = tuple(kimodo_rest[child][a] - kimodo_rest[name][a] for a in range(3))
            self.fix[j] = qbetween(ours, theirs)
        for name in FOLLOWS_PARENT:
            j = self.index[name]
            self.fix[j] = self.fix[self.parents[j]]
        # fix * rest, and its inverse: the two products every pose needs.
        self.carry = [qnorm(qmul(self.fix[j], self.rest_world[j])) for j in range(len(self.joints))]
        # Standing in the T-pose, our hips are this much higher than Kimodo's.
        self.lift = self.rest_pos[0][1] - float(kimodo_hips_y)

    def fk(self, root, rotations):
        pos, rot = [None] * len(self.joints), [None] * len(self.joints)
        for i, parent in enumerate(self.parents):
            if parent < 0:
                pos[i], rot[i] = tuple(root), qnorm(rotations[i])
            else:
                off = qrot(rot[parent], self.rest_pos[i])
                pos[i] = (pos[parent][0] + off[0], pos[parent][1] + off[1], pos[parent][2] + off[2])
                rot[i] = qnorm(qmul(rot[parent], rotations[i]))
        return pos, rot

    # ---- ours -> Kimodo ---------------------------------------------------

    def place(self, pose: dict) -> tuple:
        """One POSE of the worker's input (rotations, root, at, heading) as (hips position, local rotations), in the scene."""
        rotations = list(self.rest_rot)
        for name, q in (pose.get("rotations") or {}).items():
            if name not in self.index:
                raise ValueError(f"unknown joint {name!r}")
            if len(q) != 4 or not all(math.isfinite(float(c)) for c in q):
                raise ValueError(f"{name}: a rotation is four finite numbers [x, y, z, w]")
            rotations[self.index[name]] = qnorm(tuple(float(c) for c in q))
        root = tuple(float(c) for c in pose.get("root", self.rest_pos[0]))
        at = tuple(float(c) for c in pose.get("at", (0.0, 0.0, 0.0)))
        turn = qyaw(float(pose.get("heading", 0.0)))
        turned = qrot(turn, root)
        rotations[0] = qmul(turn, rotations[0])
        return (at[0] + turned[0], at[1] + turned[1], at[2] + turned[2]), rotations

    def to_kimodo(self, pose: dict) -> dict:
        """A POSE as Kimodo's constraint files want it: hips position, and each joint's local rotation as axis-angle."""
        root, rotations = self.place(pose)
        _, world = self.fk(root, rotations)
        turned = [qmul(world[j], qconj(self.carry[j])) for j in range(len(self.joints))]
        local = [turned[j] if p < 0 else qmul(qconj(turned[p]), turned[j]) for j, p in enumerate(self.parents)]
        return {
            "root_position": [root[0], root[1] - self.lift, root[2]],
            "local_joints_rot": [to_axis_angle(q) for q in local],
        }

    # ---- Kimodo -> ours ---------------------------------------------------

    def from_kimodo(self, root, turned) -> tuple:
        """One frame of Kimodo's answer (hips position, and each joint's world turn from the
        T-pose, in our joint order) as (root, local rotations) in the repo's motion format."""
        world = [qnorm(qmul(tuple(turned[j]), self.carry[j])) for j in range(len(self.joints))]
        local = [world[j] if p < 0 else qnorm(qmul(qconj(world[p]), world[j])) for j, p in enumerate(self.parents)]
        return (float(root[0]), float(root[1]) + self.lift, float(root[2])), local
