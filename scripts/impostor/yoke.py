"""The arithmetic of the neck piece: a yoke of the neck, the collar and the tops of both shoulders, drawn as one
piece of the model that the skeleton pulls about, where the chest's card steps aside (bake_joints.py makes it;
gallery/impostor.js and impostor.py draw it). No Blender in here: test_impostor.py tries it as it is.

Why there is one. The skeleton has a bone for the neck and one for each collar bone, and a dance uses them: the
head's turn is shared between the neck and the head, a raised arm lifts its collar bone. The cards had no part
for any of the three. Their skin was in the chest's card, which rides the chest bone alone. So the head went
where the neck took it, the arms where the collar bones took them, and the neck, the collar and the shoulder
tops stayed behind with the ribs.

What is in here:

    zone        how big the piece is: a ball about the foot of the neck
    shoulder_zone  ... and how big a shoulder's is: as the shoulders are wide, not as the arm is thick
    cut_from    which of the tidy version's meshes a piece is cut from: a top painted on the skin is skin
    spread_pull the bones' pull evened out along the piece (a neck is not a hinge)
    lay_cloth   clothing gives up some of what the neck pulls on it (a collar lies on the shoulders)
    rim         the pull eased over to the chest bone toward the piece's rim, where the chest's card is
    most        each point's four strongest bones (all a .glb carries)
    rest_again  a point moved, as it rests, so that a changed pull leaves it where it was in the pictured pose
"""

import numpy as np

ARM = 0.9          # the zone reaches this share of the way from the foot of the neck to the nearer arm's joint ...
CHEST = 0.8        # ... or this share of the way down to the chest's own joint, whichever is less
RIM = 0.3          # the pull is eased to the chest bone over this share of the zone, coming in from the rim
RIM_CLEAR_M = 0.04 # ... but not where the next piece is, nor this far past it: there the two keep the bones' own pull, and so agree
RIM_UP = 0.2       # ... nor up the neck: above the foot of the neck by this share of the zone the piece meets the head's card, not the chest's
EVEN_M = 0.03      # the pull is evened out over about this far along the surface
CLOTH = 0.5        # clothing gives this share of what the neck and head pull on it to the chest
HEAD_ASIDE = 0.65  # the head's card steps aside for the neck's piece this share of the way from the foot of the neck up to the head's joint: the neck is the piece's, the jaw and the face the card's
SHOULDER_SPAN = 0.65  # a shoulder's zone reaches at least this share of the way from its joint to the foot of the neck (shoulder_zone)


def ease(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def zone(foot, arms, chest, times=1.0):
    """The radius of the ball about the foot of the neck (m). foot, chest: where the neck bone and the chest bone
    begin; arms: where each upper arm begins."""
    foot = np.asarray(foot, dtype=np.float64)
    return times * min(ARM * min(float(np.linalg.norm(np.asarray(a) - foot)) for a in arms), CHEST * float(np.linalg.norm(np.asarray(chest) - foot)))


def shoulder_zone(zone, joint, foot, span=SHOULDER_SPAN):
    """A shoulder's zone (m): the one its ring gives (zone), but never less than `span` of the way from the joint to
    the foot of the neck. What stretches when an arm goes up (the cap of the shoulder, the deltoid, the armpit) is as
    big as the shoulders are wide, not as the arm is thick. A slim arm on a woman's shoulders made a zone of 8.5 cm
    where the skin that moves reaches 10 to 15; on the men the ring's zone is 0.69 to 0.72 of the way already."""
    return max(float(zone), span * float(np.linalg.norm(np.asarray(joint, dtype=np.float64) - np.asarray(foot, dtype=np.float64))))


def cut_from(meshes, worn, dress=()):
    """Which of a tidy version's meshes the pieces are cut from: [True or False] for meshes [(the garment it is, or
    None for skin; the garments it is the skin under)], as cloth.py writes names. worn: the garments the pictured
    model has as meshes of their own, or None when it is one skin (a clothed final.glb). dress: the dress's
    garments (bake_impostor.py: chains_of), which are a piece of their own and never cut here.

    One skin: the tidy garments are its outside (a shirt, a coat) and are cut; the skin under them is not, except
    under the dress (a knee under a skirt lies on the leg). A body with garments put back on it (rig_detailed.py:
    "dressed") has every garment that was not put back painted on its skin: her sleeveless top is the base body's
    own black, not cloth over it. Cut from the tidy garment, a piece is that garment's shape, not hers (the tidy
    top's straps are plates standing off her shoulders by up to ten centimetres, which laid onto her skin tore into
    fins), and lay_cloth would hold it back from the neck as if it were a collar. So there such a garment gives way
    to the skin it hides, which lies where her skin does and moves as skin."""
    swung = lambda g: bool(g) and any(s == g or s.startswith(g + "_") for s in dress)
    out = []
    for gear, under in meshes:
        if worn is None:
            keep = gear is not None or not under or any(swung(g) for g in under)
        elif gear is not None:
            keep = gear in worn
        else:
            keep = not under or any(g not in worn or swung(g) for g in under)
        out.append(keep and not swung(gear))
    return out


def rounds_for(even_m, edge_m):
    """How many rounds of spread_pull even the pull out over even_m, on a mesh whose edges are edge_m long."""
    return 0 if even_m <= 0 else min(80, int(np.ceil(2.0 * (even_m / max(edge_m, 1e-4)) ** 2)))


def spread_pull(pull, edges, pinned, rounds):
    """The bones' pull on each point evened out along a mesh's edges: each round a point takes half of its own and
    half of the mean of the points it shares an edge with. pull: VxB; edges: Ex2; pinned: V, True where a point
    keeps its own. A neck is not a hinge: the turn of a head is shared all the way down it, and a shoulder's lift
    along the collar. A rig that gives each point to one bone alone folds the skin where two bones' points meet."""
    pull = np.array(pull, dtype=np.float64)
    edges = np.asarray(edges, dtype=np.int64).reshape(-1, 2)
    if not len(edges) or rounds < 1:
        return pull
    count = np.bincount(edges.ravel(), minlength=len(pull)).astype(np.float64)
    free = ~np.asarray(pinned, dtype=bool) & (count > 0)
    for _ in range(rounds):
        total = np.zeros_like(pull)
        np.add.at(total, edges[:, 0], pull[edges[:, 1]])
        np.add.at(total, edges[:, 1], pull[edges[:, 0]])
        pull[free] = 0.5 * pull[free] + 0.5 * total[free] / count[free, None]
    return pull


def lay_cloth(pull, worn, neck, head, chest, share=CLOTH):
    """Cloth is not skin: a collar lies on the shoulders, and the neck turns inside it. Where a point is clothing
    (worn: V, True), `share` of what the neck and the head pull on it goes to the chest. neck, head, chest: which
    columns of pull they are."""
    pull = np.array(pull, dtype=np.float64)
    given = share * np.asarray(worn, dtype=np.float64)
    moved = given * (pull[:, neck] + pull[:, head])
    pull[:, neck] *= 1.0 - given
    pull[:, head] *= 1.0 - given
    pull[:, chest] += moved
    return pull


def rim(pull, spot, centre, radius, mine, chest, others=(), up=None, share=RIM):
    """A piece meets the chest's card at its rim, and that card rides the chest bone alone. Over the outer `share`
    of the zone the pull of the bones that card stands for (mine: their columns; the chest, the neck and both
    collar bones) is eased over to the chest bone, so there is no step where piece and card meet. Not near the
    next piece (others: [(centre, radius)]), which keeps the bones' own pull as this one then does; and, given
    `up` (the way up the neck from the centre), not above the foot of the neck. spot: Vx3, where each point rests.
    Returns (the pull, how much of each point's was eased over: 0 to 1)."""
    pull, spot = np.array(pull, dtype=np.float64), np.asarray(spot, dtype=np.float64)
    if share <= 0:
        return pull, np.zeros(len(pull))
    far = np.linalg.norm(spot - np.asarray(centre), axis=1)
    t = 1.0 - ease((radius - far) / (share * radius))
    for c, r in others:
        t = t * ease((np.linalg.norm(spot - np.asarray(c), axis=1) - r) / RIM_CLEAR_M)
    if up is not None:
        up = np.asarray(up, dtype=np.float64)
        t = t * (1.0 - ease((spot - np.asarray(centre)) @ (up / np.linalg.norm(up)) / (RIM_UP * radius) + 0.5))
    moved = t * pull[:, mine].sum(axis=1)
    pull[:, mine] *= (1.0 - t)[:, None]
    pull[:, chest] += moved
    return pull, t


def most(pull, keep=4):
    """Each point's `keep` strongest bones, adding up to one (a .glb carries four a point)."""
    out = np.array(pull, dtype=np.float64)
    if out.shape[1] > keep:
        low = np.argsort(out, axis=1)[:, :-keep]
        np.put_along_axis(out, low, 0.0, axis=1)
    return out / np.maximum(out.sum(axis=1, keepdims=True), 1e-9)


def rest_again(spot, old, new, held):
    """Where points must rest for a changed pull to put them, in one pose, exactly where the old pull did.
    spot: Vx3 as they rest now; old, new: VxB; held: Bx4x4, how each bone moves a point from rest in that pose.
    The cards were pictured with the arms hanging and the collar bones with them, and a piece is their surface in
    that pose: so it is still, whatever was done to its pull, and only differs as the bones leave it."""
    spot = np.asarray(spot, dtype=np.float64)
    was = np.einsum("vb,bij->vij", np.asarray(old, dtype=np.float64), held)
    now = np.einsum("vb,bij->vij", np.asarray(new, dtype=np.float64), held)
    there = np.einsum("vij,vj->vi", was[:, :3, :3], spot) + was[:, :3, 3]
    return np.einsum("vij,vj->vi", np.linalg.inv(now)[:, :3, :], np.concatenate([there, np.ones((len(there), 1))], axis=1))
