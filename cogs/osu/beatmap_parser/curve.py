import math


# Translated from JavaScript to Python by Awlex

def is_point_in_circle(point, center, radius):
    return distance_points(point, center) <= radius


def distance_points(p1, p2):
    x = (p1[0] - p2[0])
    y = (p1[1] - p2[1])
    return math.sqrt(x * x + y * y)


def distance_from_points(array):
    distance = 0

    for i in range(1, len(array)):
        distance += distance_points(array[i], array[i - 1])

    return distance


def angle_from_points(p1, p2):
    return math.atan2(p2[1] - p1[1], p2[0] - p1[0])


def cart_from_pol(r, teta):
    x2 = (r * math.cos(teta))
    y2 = (r * math.sin(teta))

    return [x2, y2]


def point_at_distance(array, distance):
    # needs a serious cleanup !
    global new_distance, i
    current_distance = 0

    if len(array) < 2:
        return [0, 0, 0, 0]

    if distance == 0:
        angle = angle_from_points(array[0], array[1])
        return [array[0][0], array[0][1], angle, 0]

    if distance_from_points(array) <= distance:
        angle = angle_from_points(array[array.length - 2], array[array.length - 1])
        return [array[array.length - 1][0],
                array[array.length - 1][1],
                angle,
                array.length - 2]

    for i in range(len(array) - 2):
        x = (array[i][0] - array[i + 1][0])
        y = (array[i][1] - array[i + 1][1])

        new_distance = (math.sqrt(x * x + y * y))
        current_distance += new_distance

        if distance <= current_distance:
            break

    current_distance -= new_distance

    if distance == current_distance:
        coord = [array[i][0], array[i][1]]
        angle = angle_from_points(array[i], array[i + 1])
    else:
        angle = angle_from_points(array[i], array[i + 1])
        cart = cart_from_pol((distance - current_distance), angle)

        if array[i][0] > array[i + 1][0]:
            coord = [(array[i][0] - cart[0]), (array[i][1] - cart[1])]
        else:
            coord = [(array[i][0] + cart[0]), (array[i][1] + cart[1])]

    return [coord[0], coord[1], angle, i]


def cpn(p, n):
    if p < 0 or p > n:
        return 0
    p = min(p, n - p)
    out = 1
    for i in range(1, p + 1):
        out = out * (n - p + i) / i
    return out


def array_values(array):
    out = []
    for i in array:
        out.append(array[i])
    return out


def array_calc(op, array1, array2):
    minimum = min(len(array1), len(array2))
    retour = []

    for i in range(minimum):
        retour.append(array1[i] + op * array2[i])

    return retour


# ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** *

class Bezier:
    def __init__(self, points):
        self.points = points
        self.order = len(points)

        self.step = (0.0025 / self.order) if self.order > 0 else 1  # // x0.10
        self.pos = {}
        self.calc_points()

    def at(self, t: int):

        # B(t) = sum_(i=0) ^ n(iparmisn) (1 - t) ^ (n - i) * t ^ i * P_i
        if t in self.pos:
            return self.pos[t]

        x = 0
        y = 0
        n = self.order - 1

        for i in range(n + 1):
            x += cpn(i, n) * ((1 - t) ** (n - i)) * (t ** i) * self.points[i][0]
            y += cpn(i, n) * ((1 - t) ** (n - i)) * (t ** i) * self.points[i][1]

        self.pos[t] = [x, y]

        return [x, y]

    # Changed to approximate length
    def calc_points(self):
        if len(self.pos): return

        self.pxlength = 0
        prev = self.at(0)
        i = 0
        end = 1 + self.step

        while i < end:
            current = self.at(i)
            self.pxlength += distance_points(prev, current)
            prev = current
            i += self.step
            # ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** *

    def point_at_distance(self, dist):
        return {
            0: False,
            1: self.points[0],
        }.get(self.order, self.rec(dist))

    def rec(self, dist):
        self.calc_points()
        return point_at_distance(array_values(self.pos), dist)[:2]


# ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** * #

class Catmull:
    def __init__(self, points):
        self.points = points
        self.order = len(points)

        self.step = 0.025
        self.pos = []
        self.calc_points()

    def at(self, x, t):
        v1 = self.points[x - 1] if x >= 1 else self.points[x]
        v2 = self.points[x]
        v3 = self.points[x + 1] if x + 1 < self.order else array_calc('1', v2, array_calc('-1', v2, v1))
        v4 = self.points[x + 2] if x + 2 < self.order else array_calc('1', v3, array_calc('-1', v3, v2))

        retour = []
        for i in range(2):
            retour[i] = 0.5 * (
                (-v1[i] + 3 * v2[i] - 3 * v3[i] + v4[i]) * t * t * t + (
                    2 * v1[i] - 5 * v2[i] + 4 * v3[i] - v4[i]) * t * t + (
                    -v1[i] + v3[i]) * t + 2 * v2[i])

        return retour

    def calc_points(self):
        if len(self.pos):
            return
        for i in range(self.order - 1):
            for t in range(start=0, stop=1 + self.step, step=self.step):
                self.pos.append(self.at(i, t))

    def point_at_distance(self, dist):
        return {
            0: False,
            1: self.points[0],
        }.get(self.order, self.rec(dist))

    def rec(self, dist):
        self.calc_points()
        return point_at_distance(array_values(self.pos), dist)[:2]