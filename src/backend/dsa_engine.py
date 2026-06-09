# import numpy as np

# # A small class to represent the 2D boundary of a Quad Tree node
# class Boundary:
#     def __init__(self, x_min, y_min, x_max, y_max):
#         self.x_min = x_min
#         self.y_min = y_min
#         self.x_max = x_max
#         self.y_max = y_max
#         self.center_x = (x_min + x_max) / 2
#         self.center_y = (y_min + y_max) / 2
#         self.width = x_max - x_min
#         self.height = y_max - y_min

#     def contains(self, x, y):
#         # Checks if a point (x, y) is within this boundary
#         return (self.x_min <= x <= self.x_max and
#                 self.y_min <= y <= self.y_max)

#     def intersects(self, range_boundary):
#         # Checks if this boundary overlaps with another range boundary (used for searching)
#         return not (range_boundary.x_min > self.x_max or
#                     range_boundary.x_max < self.x_min or
#                     range_boundary.y_min > self.y_max or
#                     range_boundary.y_max < self.y_min)

# class QuadTree:
#     def __init__(self, boundary: Boundary, capacity=4):
#         self.boundary = boundary
#         self.capacity = capacity
#         # Points stored in this node (format: [{'x': 100, 'y': 200, 'code': 'VER'}, ...])
#         self.points = []
#         self.divided = False

#     def subdivide(self):
#         # Recursively divides the node into four quadrants (NW, NE, SW, SE)
#         x = self.boundary.center_x
#         y = self.boundary.center_y
#         w = self.boundary.width / 2
#         h = self.boundary.height / 2

#         nw_boundary = Boundary(x - w, y, x, y + h)
#         ne_boundary = Boundary(x, y, x + w, y + h)
#         sw_boundary = Boundary(x - w, y - h, x, y)
#         se_boundary = Boundary(x, y - h, x + w, y)

#         self.northwest = QuadTree(nw_boundary, self.capacity)
#         self.northeast = QuadTree(ne_boundary, self.capacity)
#         self.southwest = QuadTree(sw_boundary, self.capacity)
#         self.southeast = QuadTree(se_boundary, self.capacity)

#         self.divided = True

#         # Redistribute existing points into the new children
#         for point in self.points:
#             self._insert_to_child(point)
#         self.points = []

#     def _insert_to_child(self, point):
#         # Helper function to insert a point into one of the children
#         if self.northwest.boundary.contains(point['x'], point['y']):
#             self.northwest.insert(point)
#         elif self.northeast.boundary.contains(point['x'], point['y']):
#             self.northeast.insert(point)
#         elif self.southwest.boundary.contains(point['x'], point['y']):
#             self.southwest.insert(point)
#         elif self.southeast.boundary.contains(point['x'], point['y']):
#             self.southeast.insert(point)

#     def insert(self, point):
#         # point is expected to be a dict with 'x', 'y', and 'code' keys
#         if not self.boundary.contains(point['x'], point['y']):
#             return False

#         if not self.divided and len(self.points) < self.capacity:
#             self.points.append(point)
#             return True
        
#         if not self.divided:
#             self.subdivide()

#         return self._insert_to_child(point)
    
#     def query_range(self, range_boundary: Boundary, found_points: list):
#         """
#         Finds all points within the specified range (range_boundary) by traversing the tree.
#         """
#         if not self.boundary.intersects(range_boundary):
#             return

#         for point in self.points:
#             if range_boundary.contains(point['x'], point['y']):
#                 found_points.append(point)

#         if self.divided:
#             self.northwest.query_range(range_boundary, found_points)
#             self.northeast.query_range(range_boundary, found_points)
#             self.southwest.query_range(range_boundary, found_points)
#             self.southeast.query_range(range_boundary, found_points)

#         return found_points

import numpy as np

# A small class to represent the 2D boundary of a Quad Tree node
class Boundary:
    def __init__(self, x_min, y_min, x_max, y_max):
        self.x_min = x_min
        self.y_min = y_min
        self.x_max = x_max
        self.y_max = y_max
        self.center_x = (x_min + x_max) / 2
        self.center_y = (y_min + y_max) / 2
        self.width = x_max - x_min
        self.height = y_max - y_min

    def contains(self, x, y):
        # Checks if a point (x, y) is within this boundary
        return (self.x_min <= x <= self.x_max and
                self.y_min <= y <= self.y_max)

    def intersects(self, range_boundary):
        # Checks if this boundary overlaps with another range boundary (used for searching)
        return not (range_boundary.x_min > self.x_max or
                    range_boundary.x_max < self.x_min or
                    range_boundary.y_min > self.y_max or
                    range_boundary.y_max < self.y_min)

class QuadTree:
    def __init__(self, boundary: Boundary, capacity=4):
        self.boundary = boundary
        self.capacity = capacity
        # Points stored in this node (format: [{'x': 100, 'y': 200, 'code': 'VER'}, ...])
        self.points = []
        self.divided = False

    def subdivide(self):
        # Recursively divides the node into four quadrants (NW, NE, SW, SE)
        x = self.boundary.center_x
        y = self.boundary.center_y
        w = self.boundary.width / 2
        h = self.boundary.height / 2

        nw_boundary = Boundary(x - w, y, x, y + h)
        ne_boundary = Boundary(x, y, x + w, y + h)
        sw_boundary = Boundary(x - w, y - h, x, y)
        se_boundary = Boundary(x, y - h, x + w, y)

        self.northwest = QuadTree(nw_boundary, self.capacity)
        self.northeast = QuadTree(ne_boundary, self.capacity)
        self.southwest = QuadTree(sw_boundary, self.capacity)
        self.southeast = QuadTree(se_boundary, self.capacity)

        self.divided = True

        # Redistribute existing points into the new children
        for point in self.points:
            self._insert_to_child(point)
        self.points = []

    def _insert_to_child(self, point):
        # Helper function to insert a point into one of the children
        if self.northwest.boundary.contains(point['x'], point['y']):
            self.northwest.insert(point)
        elif self.northeast.boundary.contains(point['x'], point['y']):
            self.northeast.insert(point)
        elif self.southwest.boundary.contains(point['x'], point['y']):
            self.southwest.insert(point)
        elif self.southeast.boundary.contains(point['x'], point['y']):
            self.southeast.insert(point)

    def insert(self, point):
        # point is expected to be a dict with 'x', 'y', and 'code' keys
        if not self.boundary.contains(point['x'], point['y']):
            return False

        if not self.divided and len(self.points) < self.capacity:
            self.points.append(point)
            return True
        
        if not self.divided:
            self.subdivide()

        return self._insert_to_child(point)
    
    def query_range(self, range_boundary: Boundary, found_points: list):
        """
        Finds all points within the specified range (range_boundary) by traversing the tree.
        """
        if not self.boundary.intersects(range_boundary):
            return

        for point in self.points:
            if range_boundary.contains(point['x'], point['y']):
                found_points.append(point)

        if self.divided:
            self.northwest.query_range(range_boundary, found_points)
            self.northeast.query_range(range_boundary, found_points)
            self.southwest.query_range(range_boundary, found_points)
            self.southeast.query_range(range_boundary, found_points)

        return found_points

# ==========================================
# NEW IMPLEMENTATIONS ADDED BELOW
# ==========================================

class DisjointSet:
    """Idea 1: Disjoint Set Union for DRS Trains"""
    def __init__(self, elements):
        self.parent = {e: e for e in elements}
        self.rank = {e: 0 for e in elements}

    def find(self, item):
        if item not in self.parent: return item
        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])
        return self.parent[item]

    def union(self, item1, item2):
        root1 = self.find(item1)
        root2 = self.find(item2)
        if root1 != root2:
            if self.rank[root1] < self.rank[root2]:
                self.parent[root1] = root2
            elif self.rank[root1] > self.rank[root2]:
                self.parent[root2] = root1
            else:
                self.parent[root2] = root1
                self.rank[root1] += 1

    def get_groups(self):
        groups = {}
        for item in self.parent:
            root = self.find(item)
            if root not in groups: groups[root] = []
            groups[root].append(item)
        return groups

class IntervalNode:
    """Idea 3: Interval Tree Node"""
    def __init__(self, start, end, data):
        self.start = start
        self.end = end
        self.max_end = end
        self.data = data
        self.left = None
        self.right = None

class IntervalTree:
    """Idea 3: Interval Tree for Sector Mapping"""
    def __init__(self):
        self.root = None

    def insert(self, start, end, data):
        if not self.root:
            self.root = IntervalNode(start, end, data)
        else:
            self._insert(self.root, start, end, data)

    def _insert(self, node, start, end, data):
        if end > node.max_end: node.max_end = end
        if start < node.start:
            if node.left is None: node.left = IntervalNode(start, end, data)
            else: self._insert(node.left, start, end, data)
        else:
            if node.right is None: node.right = IntervalNode(start, end, data)
            else: self._insert(node.right, start, end, data)

    def traverse(self):
        res = []
        self._inorder(self.root, res)
        return res

    def _inorder(self, node, res):
        if node:
            self._inorder(node.left, res)
            res.append(node)
            self._inorder(node.right, res)