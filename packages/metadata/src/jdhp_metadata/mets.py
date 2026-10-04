"""METS packaging for a digitized book (OAIS archival information package).

Phase 0 writes the structural skeleton: header, file section with the preservation masters and
their fixity, and a physical structMap of pages. Descriptive MODS and PREMIS sections join in
Phase 3 through the same builder.
"""

from __future__ import annotations

import datetime as dt
import xml.etree.ElementTree as ET  # nosec B405  # build only; parsing uses xml_security
from dataclasses import dataclass

from jdhp_metadata.xml_security import parse_xml

METS_NS = "http://www.loc.gov/METS/"
XLINK_NS = "http://www.w3.org/1999/xlink"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
METS_SCHEMA = "http://www.loc.gov/standards/mets/mets.xsd"


@dataclass(frozen=True, slots=True)
class MetsFile:
    seq: int
    key: str
    sha256: str
    size: int
    mimetype: str = "image/tiff"
    label: str | None = None


@dataclass(frozen=True, slots=True)
class MetsPackage:
    work_public_id: str
    digital_object_id: str
    created: dt.datetime
    files: tuple[MetsFile, ...]
    creator: str = "Jordanian Digital Heritage Platform ingest worker"
    title: str | None = None


def build_mets(package: MetsPackage) -> bytes:
    ET.register_namespace("mets", METS_NS)
    ET.register_namespace("xlink", XLINK_NS)
    ET.register_namespace("xsi", XSI_NS)
    root = ET.Element(
        f"{{{METS_NS}}}mets",
        {
            "OBJID": package.digital_object_id,
            "LABEL": package.title or package.work_public_id,
            "TYPE": "digitized book",
            f"{{{XSI_NS}}}schemaLocation": f"{METS_NS} {METS_SCHEMA}",
        },
    )
    header = ET.SubElement(
        root,
        f"{{{METS_NS}}}metsHdr",
        {
            "CREATEDATE": package.created.replace(microsecond=0).isoformat(),
            "RECORDSTATUS": "COMPLETE",
        },
    )
    agent = ET.SubElement(
        header, f"{{{METS_NS}}}agent", {"ROLE": "CREATOR", "TYPE": "OTHER", "OTHERTYPE": "SOFTWARE"}
    )
    ET.SubElement(agent, f"{{{METS_NS}}}name").text = package.creator
    alt = ET.SubElement(header, f"{{{METS_NS}}}altRecordID", {"TYPE": "ARK"})
    alt.text = package.work_public_id

    file_sec = ET.SubElement(root, f"{{{METS_NS}}}fileSec")
    group = ET.SubElement(file_sec, f"{{{METS_NS}}}fileGrp", {"USE": "PRESERVATION"})
    for item in package.files:
        file_el = ET.SubElement(
            group,
            f"{{{METS_NS}}}file",
            {
                "ID": f"MASTER_{item.seq:04d}",
                "SEQ": str(item.seq),
                "MIMETYPE": item.mimetype,
                "SIZE": str(item.size),
                "CHECKSUM": item.sha256,
                "CHECKSUMTYPE": "SHA-256",
            },
        )
        ET.SubElement(
            file_el,
            f"{{{METS_NS}}}FLocat",
            {"LOCTYPE": "OTHER", "OTHERLOCTYPE": "S3", f"{{{XLINK_NS}}}href": item.key},
        )

    struct = ET.SubElement(root, f"{{{METS_NS}}}structMap", {"TYPE": "PHYSICAL"})
    book = ET.SubElement(
        struct,
        f"{{{METS_NS}}}div",
        {"TYPE": "book", "LABEL": package.title or package.work_public_id},
    )
    for item in package.files:
        page_div = ET.SubElement(
            book,
            f"{{{METS_NS}}}div",
            {"TYPE": "page", "ORDER": str(item.seq), "LABEL": item.label or str(item.seq)},
        )
        ET.SubElement(page_div, f"{{{METS_NS}}}fptr", {"FILEID": f"MASTER_{item.seq:04d}"})
    return bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))


def parse_mets(data: bytes | str) -> MetsPackage:
    root = parse_xml(data)
    ns = {"mets": METS_NS, "xlink": XLINK_NS}
    header = root.find("mets:metsHdr", ns)
    created_text = header.get("CREATEDATE", "") if header is not None else ""
    created = dt.datetime.fromisoformat(created_text) if created_text else dt.datetime.now(dt.UTC)
    labels = {
        int(div.get("ORDER", "0")): div.get("LABEL")
        for div in root.findall(".//mets:structMap/mets:div/mets:div", ns)
    }
    files = []
    for file_el in root.findall(".//mets:fileGrp/mets:file", ns):
        locat = file_el.find("mets:FLocat", ns)
        seq = int(file_el.get("SEQ", "0"))
        files.append(
            MetsFile(
                seq=seq,
                key=str(locat.get(f"{{{XLINK_NS}}}href", "")) if locat is not None else "",
                sha256=str(file_el.get("CHECKSUM", "")),
                size=int(file_el.get("SIZE", "0")),
                mimetype=str(file_el.get("MIMETYPE", "application/octet-stream")),
                label=labels.get(seq),
            )
        )
    return MetsPackage(
        work_public_id=root.findtext("mets:metsHdr/mets:altRecordID", default="", namespaces=ns),
        digital_object_id=str(root.get("OBJID", "")),
        created=created,
        files=tuple(sorted(files, key=lambda f: f.seq)),
        title=root.get("LABEL"),
    )
