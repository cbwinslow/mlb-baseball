"""Port of Chadwick's small XML writer (``src/cwtools/xmlwrite.c`` and ``xmlwrite.h``).

Chadwick is Copyright (c) 2002-2023 Dr T L Turocy and the Chadwick Baseball
Bureau, licensed GPL-2.0-or-later; this module is a derivative of it and keeps
that notice. Names map onto the C functions (``xml_node_open`` -> ``xml_node_open``).

Like the C, the writer streams: every call appends to the document's output at once, so
attributes written to a node after one of its children was opened land after that child, and
node names and attribute values are written as given, with no escaping. The C writes to a
``FILE *``; here the text accumulates in ``XMLDoc.out`` and ``take`` returns what has been
written since the last call.

The C keeps closed node entries on a linked list to reuse them; ``next`` is that list.
"""


class XMLNode:
    """``XMLNode``"""

    def __init__(self, doc: "XMLDoc", depth: int) -> None:
        self.doc = doc
        self.depth = depth
        self.open = False
        self.has_children = False
        self.name = ""
        self.indent = " " * (2 * depth)
        self.next: XMLNode | None = None


class XMLDoc:
    """``XMLDoc``"""

    def __init__(self, root: str) -> None:
        """``xml_document_create``: writes the XML declaration and the root's opening tag start"""
        self.out: list[str] = []
        self.root = XMLNode(self, 0)
        self.root.open = True
        self.root.name = root
        self.out.append('<?xml version="1.0"?>\n')
        self.out.append(f"<{root}")

    def take(self) -> str:
        """The text written since the previous call"""
        text = "".join(self.out)
        self.out.clear()
        return text


def xml_document_cleanup(doc: XMLDoc) -> None:
    """``xml_document_cleanup``: closes any open nodes"""
    if doc.root.open:
        xml_node_close(doc.root)


def xml_node_open(parent: XMLNode, name: str) -> XMLNode:
    """``xml_node_open``: a child of ``parent``; closes the previous child (and its descendants)"""
    out = parent.doc.out
    if parent.next is not None:
        # A child node entry has been allocated.  Is it still open?
        # If it is, recursively close all open children.
        if parent.next.open:
            xml_node_close(parent.next)
    else:
        parent.next = XMLNode(parent.doc, parent.depth + 1)

    if not parent.has_children:
        # We still need to close the opening tag
        out.append(">\n")
        parent.has_children = True

    child = parent.next
    child.name = name
    child.open = True
    out.append(f"{child.indent}<{name}")
    return child


def xml_node_close(node: XMLNode) -> None:
    """``xml_node_close``: closes ``node``, including (recursively) all open children"""
    if not node.open:
        return
    if node.next is not None and node.next.open:
        xml_node_close(node.next)
    if node.has_children:
        node.doc.out.append(f"{node.indent}</{node.name}>\n")
    else:
        node.doc.out.append("/>\n")
    node.has_children = False
    node.open = False


def xml_node_cdata(node: XMLNode, data: str) -> None:
    """``xml_node_cdata``"""
    if node.next is not None and node.next.open:
        xml_node_close(node.next)
    if not node.has_children:
        # We still need to close the opening tag
        node.doc.out.append(">\n")
        node.has_children = True
    node.doc.out.append(f"{node.indent}  {data}\n")


def xml_node_attribute(node: XMLNode, attr: str, value: str) -> None:
    """``xml_node_attribute``"""
    if not node.open:
        return
    node.doc.out.append(f' {attr}="{value}"')


def xml_node_attribute_int(node: XMLNode, attr: str, value: int) -> None:
    """``xml_node_attribute_int``"""
    if not node.open:
        return
    node.doc.out.append(f' {attr}="{value}"')


def xml_node_attribute_posint(node: XMLNode, attr: str, value: int) -> None:
    """``xml_node_attribute_posint``: nothing for a negative value (a null statistic)"""
    if not node.open or value < 0:
        return
    node.doc.out.append(f' {attr}="{value}"')


def xml_node_attribute_fmt(node: XMLNode, attr: str, value: str) -> None:
    """``xml_node_attribute_fmt`` with the formatting already done by the caller (the C formats
    into a 1024-byte buffer; the port has no limit). Unlike the others it does not check that
    the node is open."""
    node.doc.out.append(f' {attr}="{value}"')
