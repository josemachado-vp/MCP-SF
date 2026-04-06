"""Tests for the metadata XML parser."""

import pytest

from helpers.metadata_parser import parse_metadata_xml, extract_entity_names

SAMPLE_METADATA_XML = """<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="1.0" xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
  <edmx:DataServices m:DataServiceVersion="2.0"
    xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">
    <Schema Namespace="SFOData"
      xmlns="http://schemas.microsoft.com/ado/2008/09/edm"
      xmlns:sap="http://www.sap.com/Protocols/SAPData">
      <EntityType Name="EmpJob">
        <Key>
          <PropertyRef Name="seqNumber"/>
          <PropertyRef Name="userId"/>
        </Key>
        <Property Name="userId" Type="Edm.String" Nullable="false"
          sap:label="User ID" sap:creatable="true" sap:updatable="false"
          sap:visible="true" sap:filterable="true"/>
        <Property Name="payGroup" Type="Edm.String" Nullable="true"
          sap:label="Pay Group" sap:creatable="true" sap:updatable="true"
          sap:visible="true" sap:filterable="false"/>
        <Property Name="employeeClass" Type="Edm.String" Nullable="true"
          sap:label="Employee Class" sap:creatable="true" sap:updatable="true"
          sap:visible="true" sap:required="true"/>
        <NavigationProperty Name="companyNav"
          Relationship="SFOData.EmpJob_companyNav"
          FromRole="EmpJob" ToRole="FOCompany"/>
      </EntityType>
      <EntityType Name="FOCompany">
        <Key><PropertyRef Name="externalCode"/></Key>
        <Property Name="externalCode" Type="Edm.String" Nullable="false"
          sap:label="Code" sap:creatable="true" sap:updatable="false"/>
        <Property Name="name" Type="Edm.String" Nullable="true"
          sap:label="Name" sap:creatable="true" sap:updatable="true"/>
      </EntityType>
      <Association Name="EmpJob_companyNav">
        <End Type="SFOData.EmpJob" Multiplicity="*" Role="EmpJob"/>
        <End Type="SFOData.FOCompany" Multiplicity="1" Role="FOCompany"/>
      </Association>
      <EntityContainer Name="API" m:IsDefaultEntityContainer="true">
        <EntitySet Name="EmpJob" EntityType="SFOData.EmpJob"/>
        <EntitySet Name="FOCompany" EntityType="SFOData.FOCompany"/>
      </EntityContainer>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>"""


class TestParseMetadataXml:
    def test_extracts_entity_types(self):
        result = parse_metadata_xml(SAMPLE_METADATA_XML)
        assert "EmpJob" in result["entities"]
        assert "FOCompany" in result["entities"]

    def test_extracts_keys(self):
        result = parse_metadata_xml(SAMPLE_METADATA_XML)
        assert result["entities"]["EmpJob"]["keys"] == ["seqNumber", "userId"]
        assert result["entities"]["FOCompany"]["keys"] == ["externalCode"]

    def test_extracts_properties(self):
        result = parse_metadata_xml(SAMPLE_METADATA_XML)
        props = result["entities"]["EmpJob"]["properties"]
        names = [p["name"] for p in props]
        assert "userId" in names
        assert "payGroup" in names
        assert "employeeClass" in names

    def test_extracts_sap_annotations(self):
        result = parse_metadata_xml(SAMPLE_METADATA_XML)
        props = result["entities"]["EmpJob"]["properties"]
        pay_group = next(p for p in props if p["name"] == "payGroup")
        assert pay_group["label"] == "Pay Group"
        assert pay_group["creatable"] is True
        assert pay_group["updatable"] is True
        assert pay_group["nullable"] is True

    def test_extracts_required_annotation(self):
        result = parse_metadata_xml(SAMPLE_METADATA_XML)
        props = result["entities"]["EmpJob"]["properties"]
        emp_class = next(p for p in props if p["name"] == "employeeClass")
        assert emp_class["required"] is True

    def test_resolves_navigation_targets(self):
        result = parse_metadata_xml(SAMPLE_METADATA_XML)
        nav_props = result["entities"]["EmpJob"]["navigation_properties"]
        company_nav = next(np for np in nav_props if np["name"] == "companyNav")
        assert company_nav["target_entity"] == "FOCompany"

    def test_extracts_entity_sets(self):
        result = parse_metadata_xml(SAMPLE_METADATA_XML)
        assert "EmpJob" in result["entity_sets"]
        assert "FOCompany" in result["entity_sets"]

    def test_non_nullable_property(self):
        result = parse_metadata_xml(SAMPLE_METADATA_XML)
        props = result["entities"]["EmpJob"]["properties"]
        user_id = next(p for p in props if p["name"] == "userId")
        assert user_id["nullable"] is False


class TestExtractEntityNames:
    def test_returns_sorted_names(self):
        names = extract_entity_names(SAMPLE_METADATA_XML)
        assert names == ["EmpJob", "FOCompany"]

    def test_empty_xml(self):
        xml = """<?xml version="1.0"?>
        <edmx:Edmx Version="1.0" xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
          <edmx:DataServices xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">
            <Schema Namespace="SFOData" xmlns="http://schemas.microsoft.com/ado/2008/09/edm">
              <EntityContainer Name="API" m:IsDefaultEntityContainer="true"/>
            </Schema>
          </edmx:DataServices>
        </edmx:Edmx>"""
        names = extract_entity_names(xml)
        assert names == []
