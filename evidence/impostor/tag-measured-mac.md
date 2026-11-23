
Poses sampled once and shared (ms of work a frame; in brackets: moving the skeletons + placing):

| runners | 10 | 50 | 100 | 250 | 500 | 1000 |
|---|---|---|---|---|---|---|
| Meshes, one by one | 3.9 (0.1 + 0.1) | 8.6 (0.4 + 0.1) | 8.4 (0.2 + 0.0) | 14.0 (0.7 + 0.0) | 15.4 (1.0 + 0.0) | not run |
| Meshes, all at once | 3.4 (0.0 + 0.1) | 4.8 (0.0 + 0.1) | 6.2 (0.0 + 0.0) | 8.3 (0.0 + 0.1) | 9.0 (0.0 + 0.1) | 8.7 (0.0 + 0.1) |
| Cards, one by one | 4.2 (0.0 + 0.5) | 8.7 (0.0 + 1.1) | 12.7 (0.0 + 1.7) | 15.3 (0.0 + 2.8) | 34.0 (0.0 + 7.0) | not run |
| Cards, all at once | 3.6 (0.0 + 0.1) | 5.5 (0.0 + 0.1) | 7.0 (0.0 + 0.1) | 6.1 (0.0 + 0.3) | 7.9 (0.0 + 0.5) | 12.7 (0.0 + 0.6) |
| Cards, all at once, search off far away | 2.1 (0.0 + 0.0) | 2.5 (0.0 + 0.1) | 4.7 (0.0 + 0.2) | 5.7 (0.0 + 0.3) | 4.9 (0.0 + 0.5) | 6.3 (0.0 + 0.7) |

Each runner works his own skeleton out (ms of work a frame; in brackets: moving the skeletons + placing):

| runners | 10 | 50 | 100 | 250 | 500 | 1000 |
|---|---|---|---|---|---|---|
| Meshes, one by one | 5.2 (0.4 + 0.0) | 7.1 (1.4 + 0.0) | 9.2 (1.5 + 0.0) | 15.5 (2.4 + 0.0) | 18.6 (3.5 + 0.0) | not run |
| Meshes, all at once | 3.1 (0.3 + 0.1) | 7.2 (2.0 + 0.5) | 9.9 (2.9 + 1.0) | 10.2 (2.5 + 0.8) | 13.4 (4.3 + 1.3) | 20.2 (7.2 + 5.2) |
| Cards, one by one | 5.3 (0.4 + 0.7) | 9.0 (0.5 + 1.2) | 12.2 (0.7 + 1.7) | 21.1 (1.7 + 4.4) | 43.5 (3.6 + 9.5) | not run |
| Cards, all at once | 3.8 (0.5 + 0.1) | 6.7 (1.1 + 0.3) | 9.6 (2.1 + 0.8) | 10.1 (2.2 + 1.0) | 13.1 (4.3 + 2.2) | 16.2 (6.4 + 3.8) |
| Cards, all at once, search off far away | 3.0 (0.4 + 0.1) | 4.1 (1.3 + 0.3) | 5.9 (2.2 + 0.9) | 7.0 (2.7 + 1.0) | 9.8 (4.2 + 1.7) | 14.3 (6.4 + 4.1) |

Draws and triangles a frame (shared poses):

| runners | 10 | 50 | 100 | 250 | 500 | 1000 |
|---|---|---|---|---|---|---|
| Meshes, one by one | 84 draws, 158k | 404 draws, 786k | 804 draws, 1.6M | 2,004 draws, 3.9M | 4,004 draws, 7.8M |  |
| Meshes, all at once | 12 draws, 158k | 12 draws, 786k | 12 draws, 1.6M | 12 draws, 3.9M | 12 draws, 7.8M | 12 draws, 15.7M |
| Cards, one by one | 164 draws, 2k | 804 draws, 3k | 1,604 draws, 4k | 4,004 draws, 9k | 8,004 draws, 17k |  |
| Cards, all at once | 5 draws, 2k | 5 draws, 3k | 5 draws, 4k | 5 draws, 9k | 5 draws, 17k | 5 draws, 33k |
| Cards, all at once, search off far away | 5 draws, 2k | 5 draws, 3k | 5 draws, 4k | 5 draws, 9k | 5 draws, 17k | 5 draws, 33k |

The looks (ms of work a frame, shared poses):

| look | meshes, all at once, 100 | meshes, all at once, 1000 | cards, all at once, 100 | cards, all at once, 1000 | cards, all at once, search off far away, 100 | cards, all at once, search off far away, 1000 |
|---|---|---|---|---|---|---|
| Comic | 6.2 | 9.6 | 7.2 | 10.1 | 3.0 | 7.2 |
| Pixels, baked | 6.1 | 9.3 | 3.8 | 6.3 | 3.1 | 5.1 |
| Pixels, on screen | 4.9 | 9.1 | 5.3 | 8.5 | 3.8 | 5.6 |
| Pixels, both | 5.1 | 8.0 | 3.4 | 5.9 | 3.2 | 5.4 |
| Bold ink | 5.1 | 8.0 | 7.8 | 9.6 | 4.2 | 7.3 |

picture [1080, 608] frame cap: fps of the lightest 60.4
slow 5% of work, 1000 shared: {'mesh-batch': 12.9, 'card-batch': 24.9, 'card-far': 11.7}
fps 1000 shared: {'mesh-batch': (60, 17.8), 'card-batch': (57.7, 26.6), 'card-far': (60, 17.6)}

The batched ways again on a picture of 2160 by 1216:


| runners | 10 | 100 | 250 | 1000 |
|---|---|---|---|---|
| Meshes, all at once | 5.0 (0.0 + 0.1) | 7.8 (0.0 + 0.1) | 9.2 (0.0 + 0.0) | 11.0 (0.0 + 0.1) |
| Cards, all at once | 5.3 (0.0 + 0.0) | 9.0 (0.0 + 0.1) | 9.3 (0.0 + 0.3) | 12.5 (0.0 + 1.0) |
