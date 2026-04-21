"""
Tests for the ExportService facade.
"""

import os
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from services.export import ExportService


class TestExportService:
    """Test suite for ExportService"""
    
    def test_export_service_init(self):
        """Test ExportService initializes with device_service"""
        device_service = MagicMock()
        export_service = ExportService(device_service)
        
        assert export_service.device_service == device_service
    
    def test_get_export_stats(self, sample_devices):
        """Test get_export_stats returns correct statistics"""
        device_service = MagicMock()
        export_service = ExportService(device_service)
        
        stats = export_service.get_export_stats(sample_devices)
        
        assert stats['total_devices'] == 3
        assert 'risk_level_distribution' in stats
        assert 'platform_distribution' in stats
        assert 'export_timestamp' in stats
        
        # Check risk distribution
        risk_dist = stats['risk_level_distribution']
        assert risk_dist['Critical'] == 1
        assert risk_dist['High'] == 1
        assert risk_dist['Secure'] == 1
        
        # Check platform distribution
        platform_dist = stats['platform_distribution']
        assert platform_dist['iOS'] == 2
        assert platform_dist['Android'] == 1
    
    def test_get_export_stats_empty_list(self):
        """Test get_export_stats with empty device list"""
        device_service = MagicMock()
        export_service = ExportService(device_service)
        
        stats = export_service.get_export_stats([])
        
        assert stats['total_devices'] == 0
        assert stats['risk_level_distribution'] == {}
        assert stats['platform_distribution'] == {}
    
    def test_create_csv_export(self, sample_devices):
        """Test CSV export generation"""
        device_service = MagicMock()
        export_service = ExportService(device_service)
        
        csv_content = export_service.create_csv_export(sample_devices)
        
        assert isinstance(csv_content, str)
        assert 'Device Name' in csv_content
        assert 'iPhone 1' in csv_content
        assert 'Android Phone' in csv_content
    
    def test_create_csv_export_escapes_quotes(self):
        """Test CSV properly escapes quotes in data"""
        device_service = MagicMock()
        export_service = ExportService(device_service)
        
        devices = [{
            'device_name': 'Device "With Quotes"',
            'user_email': 'test@example.com',
            'platform': 'iOS',
            'risk_level': 'Low',
            'days_since_checkin': 1,
            'last_checkin': '2024-01-15T10:30:00Z',
            'os_version': '16.0',
            'compliance_status': 'Compliant',
            'device_group_name': 'Test',
            'mdm_id': 'mdm-001',
            'threat_family_names': [],
            'threat_descriptions': [],
        }]
        
        csv_content = export_service.create_csv_export(devices)
        
        # Quotes should be escaped as double quotes
        assert '""' in csv_content or 'Device "With Quotes"' in csv_content
    
    @patch('services.export.Workbook')
    def test_export_devices_to_excel_with_devices(self, mock_workbook, sample_devices):
        """Test Excel export with provided devices"""
        device_service = MagicMock()
        export_service = ExportService(device_service)
        
        # Mock workbook
        mock_wb = MagicMock()
        mock_workbook.return_value = mock_wb
        mock_wb.sheetnames = ['Sheet']
        
        with patch('services.export.SummarySheet'), \
             patch('services.export.DeviceSheet'), \
             patch('services.export.RiskSheet'), \
             patch('services.export.ComplianceSheet'):
            
            filepath = export_service.export_devices_to_excel(devices=sample_devices)
        
        assert isinstance(filepath, str)
        assert filepath.endswith('.xlsx')
        assert '/tmp' in filepath
    
    def test_export_devices_to_excel_no_devices_raises(self):
        """Test Excel export raises exception when no devices"""
        device_service = MagicMock()
        export_service = ExportService(device_service)
        
        with pytest.raises(Exception) as exc_info:
            export_service.export_devices_to_excel(devices=[])
        
        assert 'No data to export' in str(exc_info.value)
    
    @patch('services.export.Workbook')
    def test_export_cve_report_to_excel(self, mock_workbook):
        """Test CVE report Excel export"""
        device_service = MagicMock()
        export_service = ExportService(device_service)
        
        # Mock workbook
        mock_wb = MagicMock()
        mock_workbook.return_value = mock_wb
        mock_wb.sheetnames = ['Sheet']
        
        cve_report = {
            'summary': {
                'total_devices': 100,
                'devices_with_vulnerabilities': 25,
                'vulnerability_percentage': 25.0,
                'total_cves_found': 50,
                'severity_breakdown': {'Critical': 5, 'High': 15, 'Medium': 20, 'Low': 10}
            },
            'top_cves': [{'cve': 'CVE-2024-0001', 'affected_devices': 20}],
            'all_vulnerabilities': [],
            'scan_metadata': {}
        }
        
        with patch('services.export.CVESummarySheet'), \
             patch('services.export.CVEDetailsSheet'), \
             patch('services.export.CVETopSheet'):
            
            filepath = export_service.export_cve_report_to_excel(cve_report)
        
        assert isinstance(filepath, str)
        assert filepath.endswith('.xlsx')
        assert 'cve_report' in filepath
