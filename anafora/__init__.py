import collections
import itertools
import os

try:
    import xml.etree.cElementTree as ElementTree
except ImportError:
    import xml.etree.ElementTree as ElementTree


def walk(anafora_dir):
    """
    :param anafora_dir: directory containing Anafora XML directories
    :return: an iterator of (dir-path, sub-dir, file-name) for the XML files in the directories
    """
    for subdir in os.listdir(anafora_dir):
        if os.path.isdir(os.path.join(anafora_dir, subdir)):
            for xml_name in os.listdir(os.path.join(anafora_dir, subdir)):
                if not xml_name.endswith(".xml"):
                    continue
                yield anafora_dir, subdir, xml_name


class _XMLWrapper(object):
    def __init__(self, xml):
        """
        :param xml.etree.ElementTree.Element xml: the XML element to be wrapped in an object
        """
        self.xml = xml

    def __repr__(self):
        return ElementTree.tostring(self.xml)

    def _key(self):
        raise NotImplementedError

    def __eq__(self, other):
        return isinstance(other, _XMLWrapper) and self._key() == other._key()

    def __ne__(self, other):
        return isinstance(other, _XMLWrapper) and self._key() != other._key()

    def __hash__(self):
        def _hash(obj):
            if isinstance(obj, (set, tuple, list)):
                return hash(frozenset(_hash(item) for item in obj))
            elif isinstance(obj, dict):
                return hash(frozenset(_hash(item) for item in obj.items()))
            else:
                return hash(obj)

        return _hash(self._key())


class AnaforaData(_XMLWrapper):
    def __init__(self, xml=None):
        """
        :param xml.etree.ElementTree.Element xml: the <data> element
        """
        if xml is None:
            xml = ElementTree.Element("data")
        _XMLWrapper.__init__(self, xml)
        self.annotations = AnaforaAnnotations(self.xml.find("annotations"), self)

    @classmethod
    def from_file(cls, xml_path):
        return cls(ElementTree.parse(xml_path).getroot())

    @property
    def entities(self):
        return itertools.ifilter(lambda ann: isinstance(ann, AnaforaEntity), self.annotations)

    @property
    def relations(self):
        return itertools.ifilter(lambda ann: isinstance(ann, AnaforaRelation), self.annotations)


class AnaforaAnnotations(_XMLWrapper):
    def __init__(self, xml, _data):
        _XMLWrapper.__init__(self, xml)
        self._data = _data
        self._id_to_annotation = collections.OrderedDict()
        if self.xml is not None:
            for annotation_elem in self.xml:
                if annotation_elem.tag == "entity":
                    annotation = AnaforaEntity(annotation_elem, self)
                elif annotation_elem.tag == "relation":
                    annotation = AnaforaRelation(annotation_elem, self)
                else:
                    raise ValueError("invalid tag: {0}".format(annotation_elem.tag))
                self._id_to_annotation[annotation.id] = annotation

    def __iter__(self):
        return iter(self._id_to_annotation.values())

    def append(self, annotation):
        """
        :param AnaforaAnnotation annotation: the annotation to add
        """
        if annotation.id is None:
            raise ValueError("no id defined for {0}".format(annotation))
        annotation._annotations = self
        if self.xml is None:
            self.xml = ElementTree.SubElement(self._data.xml, "annotations")
        self.xml.append(annotation.xml)
        self._id_to_annotation[annotation.id] = annotation

    def remove(self, annotation):
        """
        :param AnaforaAnnotation annotation: the annotation to remove
        """
        if annotation.id is None:
            raise ValueError("no id defined for {0}".format(annotation))
        self.xml.remove(annotation.xml)
        del self._id_to_annotation[annotation.id]


class AnaforaAnnotation(_XMLWrapper):
    def __init__(self, xml, _annotations):
        """
        :param xml.etree.ElementTree.Element xml: xml definition of this annotation
        :param AnaforaAnnotations _annotations: the annotations collection containing this annotation
        """
        _XMLWrapper.__init__(self, xml)
        self._annotations = _annotations
        self.properties = AnaforaProperties(self.xml.find("properties"), self)

    def _key(self):
        return self.type, self.parents_type, self.properties

    @property
    def id(self):
        return self.xml.findtext("id")

    @id.setter
    def id(self, value):
        id_elem = self.xml.find("id")
        if id_elem is None:
            id_elem = ElementTree.SubElement(self.xml, "id")
        id_elem.text = value

    @property
    def type(self):
        return self.xml.findtext("type")

    @type.setter
    def type(self, value):
        type_elem = self.xml.find("type")
        if type_elem is None:
            type_elem = ElementTree.SubElement(self.xml, "type")
        type_elem.text = value

    @property
    def parents_type(self):
        return self.xml.findtext("parentsType")

    @parents_type.setter
    def parents_type(self, value):
        parents_type_elem = self.xml.find("parentsType")
        if parents_type_elem is None:
            parents_type_elem = ElementTree.SubElement(self.xml, "parentsType")
        parents_type_elem.text = value


class AnaforaProperties(_XMLWrapper):
    def __init__(self, xml, _annotation):
        """
        :param xml.etree.ElementTree.Element xml: a <properties> element
        :param AnaforaAnnotation _annotation: the annotation containing these properties
        """
        _XMLWrapper.__init__(self, xml)
        self._annotation = _annotation
        self._tag_to_property_xml = {}
        if self.xml is not None:
            for property_elem in self.xml:
                self._tag_to_property_xml[property_elem.tag] = property_elem

    def _key(self):
        return frozenset(self.items())

    def __iter__(self):
        return iter(self._tag_to_property_xml)

    def __getitem__(self, property_name):
        value = self._tag_to_property_xml[property_name].text
        return self._annotation._annotations._id_to_annotation.get(value, value)

    def __setitem__(self, name, value):
        if isinstance(value, AnaforaAnnotation):
            if self._annotation is None or self._annotation._annotations is None:
                message = 'annotation must be in <annotations> before assigning annotation value to property "{0}":\n{1}'
                raise ValueError(message.format(name, self._annotation))
            if value != self._annotation._annotations._id_to_annotation.get(value.id):
                message = 'annotation must be in <annotations> before assigning it to property "{0}":\n{1}'
                raise ValueError(message.format(name, value))
        if self.xml is None:
            self.xml = ElementTree.SubElement(self._annotation.xml, "properties")
        property_elem = self.xml.find(name)
        if property_elem is None:
            property_elem = ElementTree.SubElement(self.xml, name)
            self._tag_to_property_xml[name] = property_elem
        if isinstance(value, AnaforaAnnotation):
            property_elem.text = value.id
        else:
            property_elem.text = value

    def items(self):
        return [(name, self[name]) for name in self]


class AnaforaEntity(AnaforaAnnotation):
    def __init__(self, xml=None, _annotations=None):
        if xml is None:
            xml = ElementTree.Element("entity")
        AnaforaAnnotation.__init__(self, xml, _annotations)

    def _key(self):
        return (self.spans,) + AnaforaAnnotation._key(self)

    @property
    def spans(self):
        span_elem = self.xml.findtext("span")
        if span_elem is None:
            return ()
        return tuple(int(offset) for span_text in span_elem.split(";") for offset in tuple(span_text.split(",")))


class AnaforaRelation(AnaforaAnnotation):
    def __init__(self, xml=None, _annotations=None):
        if xml is None:
            xml = ElementTree.Element("relation")
        AnaforaAnnotation.__init__(self, xml, _annotations)

    @property
    def spans(self):
        return tuple(self.properties[name].spans
                     for name in sorted(self.properties)
                     if isinstance(self.properties[name], AnaforaEntity))