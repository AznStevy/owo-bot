import math
from .curve import Bezier


# Translated from JavaScript to Python by Awlex

def get_end_point(slider_type, slider_length, points):
    if not slider_type or not slider_length or not points:
        return

    if slider_type == 'linear':
        return point_on_line(points[0], points[1], slider_length)
    elif slider_type == 'catmull':
        # not supported, anyway, it 's only used in old beatmaps
        return 'undefined'
    elif slider_type == 'bezier':
        if not points or len(points) < 2:
            return 'undefined'

        if len(points) == 2:
            return point_on_line(points[0], points[1], slider_length)

        pts = points[:]
        previous = []
        i = 0
        l = len(pts)
        while i < l:
            point = pts[i]

            if not previous:
                previous = point
                continue

            if point[0] == previous[0] and point[1] == previous[1]:
                bezier = Bezier(pts[0:i])
                pts = pts[i:]
                slider_length -= bezier.pxlength
                i = 0
                l = len(pts)

            previous = point
            i += 1

        bezier = Bezier(pts)
        return bezier.point_at_distance(slider_length)

    elif slider_type == 'pass-through':
        if not points or len(points) < 2:
            return 'undefined'

        if len(points) == 2:
            return point_on_line(points[0], points[1], slider_length)

        if len(points) > 3:
            return get_end_point('bezier', slider_length, points)

        p1 = points[0]
        p2 = points[1]
        p3 = points[2]

        cx, cy, radius = get_circum_circle(p1, p2, p3)
        radians = slider_length / radius
        if is_left(p1, p2, p3):
            radians *= -1

        return rotate(cx, cy, p1[0], p1[1], radians)


def point_on_line(p1, p2, length):
    full_length = math.sqrt(math.pow(p2[0] - p1[0], 2) + math.pow(p2[1] - p1[1], 2))
    n = full_length - length

    x = (n * p1[0] + length * p2[0]) / full_length
    y = (n * p1[1] + length * p2[1]) / full_length
    return [x, y]


# Get coordinates of a point in a circle, given the center, a startpoint and a distance in radians
# @param {Float} cx       center x
# @param {Float} cy       center y
# @param {Float} x        startpoint x
# @param {Float} y        startpoint y
# @param {Float} radians  distance from the startpoint
# @return {Object} the new point coordinates after rotation
def rotate(cx, cy, x, y, radians):
    cos = math.cos(radians)
    sin = math.sin(radians)

    return [
        (cos * (x - cx)) - (sin * (y - cy)) + cx,
        (sin * (x - cx)) + (cos * (y - cy)) + cy
    ]


# Check if C is on left side of [AB]
# @param {Object} a startpoint of the segment
# @param {Object} b endpoint of the segment
# @param {Object} c the point we want to locate
# @return {Boolean} true if on left side
def is_left(a, b, c):
    return ((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) < 0


# Get circum circle of 3 points
# @param  {Object} p1 first point
# @param  {Object} p2 second point
# @param  {Object} p3 third point
# @return {Object} circumCircle
def get_circum_circle(p1, p2, p3):
    x1 = p1[0]
    y1 = p1[1]

    x2 = p2[0]
    y2 = p2[1]

    x3 = p3[0]
    y3 = p3[1]

    # center of circle
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))

    ux = ((x1 * x1 + y1 * y1) * (y2 - y3) + (x2 * x2 + y2 * y2) * (y3 - y1) + (x3 * x3 + y3 * y3) * (y1 - y2)) / d
    uy = ((x1 * x1 + y1 * y1) * (x3 - x2) + (x2 * x2 + y2 * y2) * (x1 - x3) + (x3 * x3 + y3 * y3) * (x2 - x1)) / d

    px = ux - x1
    py = uy - y1
    r = math.sqrt(px * px + py * py)

    return ux, uy, r