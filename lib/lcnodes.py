"""LeetCode's node types, plus the serialization they use in test data.

Solutions import TreeNode/ListNode/Node from here rather than defining their
own, so the harness and the solution share one class object -- otherwise an
`isinstance(x, TreeNode)` check in a solution would silently be False.
"""

from __future__ import annotations

from collections import deque


class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right

    def __repr__(self):
        return f"TreeNode({serialize_tree(self)})"


class ListNode:
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next

    def __repr__(self):
        return f"ListNode({serialize_list(self)})"


class Node:
    """Catch-all for problems that call their node type `Node`.

    Covers the three shapes LeetCode uses it for: adjacency (clone graph),
    next-pointer trees (populating next right pointers), and random-pointer
    linked lists (copy list with random pointer).
    """

    def __init__(self, val=0, neighbors=None, left=None, right=None,
                 next=None, random=None, children=None):
        self.val = val
        self.neighbors = neighbors if neighbors is not None else []
        self.left = left
        self.right = right
        self.next = next
        self.random = random
        self.children = children if children is not None else []

    def __repr__(self):
        return f"Node({self.val})"


# --------------------------------------------------------------------------
# Binary trees -- level order with explicit nulls, trailing nulls trimmed.
# [4,2,7,1,3,6,9] / [] / [1,null,2,3]
# --------------------------------------------------------------------------

def build_tree(values):
    if not values:
        return None
    it = iter(values)
    root = TreeNode(next(it))
    queue = deque([root])
    while queue:
        node = queue.popleft()
        try:
            left = next(it)
        except StopIteration:
            break
        if left is not None:
            node.left = TreeNode(left)
            queue.append(node.left)
        try:
            right = next(it)
        except StopIteration:
            break
        if right is not None:
            node.right = TreeNode(right)
            queue.append(node.right)
    return root


def serialize_tree(root):
    if root is None:
        return []
    out = []
    queue = deque([root])
    while queue:
        node = queue.popleft()
        if node is None:
            out.append(None)
            continue
        out.append(node.val)
        queue.append(node.left)
        queue.append(node.right)
    while out and out[-1] is None:
        out.pop()
    return out


# --------------------------------------------------------------------------
# Linked lists
# --------------------------------------------------------------------------

def build_list(values):
    head = None
    for v in reversed(values or []):
        head = ListNode(v, head)
    return head


def serialize_linked_list(head, limit=10_000):
    """Serialize, but refuse to hang on a solution that created a cycle."""
    out = []
    seen = set()
    node = head
    while node is not None:
        if id(node) in seen or len(out) > limit:
            out.append("...<cycle>")
            break
        seen.add(id(node))
        out.append(node.val)
        node = node.next
    return out


# Short alias used in TreeNode/ListNode __repr__.
serialize_list = serialize_linked_list
