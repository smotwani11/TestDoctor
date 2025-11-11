#!/usr/bin/env python3
"""
Test suite for 2GPTestDoctor
Tests the annotation merging and fixing logic
"""

import unittest
import tempfile
import os
from testdoctor import TestDoctorFixer, Issue

class TestAnnotationMerging(unittest.TestCase):
    """Test cases for annotation list merging"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.fixer = TestDoctorFixer()
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up temp files"""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_find_annotation_list_simple(self):
        """Test finding a simple annotation list"""
        lines = [
            "package test;",
            "",
            "@MqTypeMappingList({",
            "    @MqTypeMapping(type = A, handler = B.class)",
            "})",
            "public class Test {",
        ]
        idx = self.fixer._find_annotation_list(lines, '@MqTypeMappingList')
        self.assertEqual(idx, 2)
    
    def test_find_annotation_list_not_found(self):
        """Test when annotation list doesn't exist"""
        lines = [
            "package test;",
            "public class Test {",
        ]
        idx = self.fixer._find_annotation_list(lines, '@MqTypeMappingList')
        self.assertIsNone(idx)
    
    def test_find_closing_brace_simple(self):
        """Test finding closing brace for simple annotation"""
        lines = [
            "@MqTypeMappingList({",
            "    @MqTypeMapping(type = A, handler = B.class)",
            "})",
            "public class Test {",
        ]
        idx = self.fixer._find_closing_brace(lines, 0)
        self.assertEqual(idx, 2)
    
    def test_find_closing_brace_multiline_annotation(self):
        """Test finding closing brace with multi-line annotation parameters"""
        lines = [
            "@MqCustomCountDownLatchList({",
            "    @MqCustomCountDownLatch(timeout = 600,",
            "                            name = LATCH_NAME,",
            "                            initialCount = 1)",
            "})",
            "public class Test {",
        ]
        idx = self.fixer._find_closing_brace(lines, 0)
        self.assertEqual(idx, 4)
    
    def test_find_closing_brace_nested_braces(self):
        """Test finding closing brace with nested structures"""
        lines = [
            "@MqTypeMappingList({",
            "    @MqTypeMapping(type = MessageQueueTypeEnum.PACKAGE_INSTALL, handler = Handler.class),",
            "    @MqTypeMapping(type = MessageQueueTypeEnum.PACKAGE_UNINSTALL, handler = Handler2.class)",
            "})",
            "public class Test {",
        ]
        idx = self.fixer._find_closing_brace(lines, 0)
        self.assertEqual(idx, 3)
    
    def test_merge_into_existing_mqtypemapping(self):
        """Test merging PACKAGE_INSTALL mappings into existing @MqTypeMappingList"""
        test_file = os.path.join(self.temp_dir, "Test.java")
        content = """package test;

import common.messaging.annotations.MqTypeMapping;
import common.messaging.annotations.MqTypeMappingList;
import common.udd.constants.messaging.MessageQueueTypeEnum;

@MqTypeMappingList({
    @MqTypeMapping(type = MessageQueueTypeEnum.PACKAGE_EXPORT, handler = ExportHandler.class)
})
public class Test extends BaseTest {
}
"""
        with open(test_file, 'w') as f:
            f.write(content)
        
        issue = Issue(rule_name="Rule Test", severity="high", 
            file_path=test_file,
            line_number=7,
            rule=3,
            description="Missing PACKAGE_INSTALL mappings",
            fix_available=True
        )
        
        # Apply fix
        result = self.fixer._fix_rule3(issue, dry_run=False)
        self.assertTrue(result)
        
        # Read result
        with open(test_file, 'r') as f:
            result_content = f.read()
        
        # Verify PACKAGE_INSTALL mappings were added
        self.assertIn('MessageQueueTypeEnum.PACKAGE_INSTALL', result_content)
        self.assertIn('MessageQueueTypeEnum.PACKAGE_INSTALL_DEFAULT', result_content)
        self.assertIn('MessageQueueTypeEnum.PACKAGE_INSTALL_SMALL', result_content)
        self.assertIn('MessageQueueTypeEnum.PACKAGE_INSTALL_LARGE', result_content)
        
        # Verify original mapping is still there
        self.assertIn('PACKAGE_EXPORT', result_content)
        
        # Verify only one @MqTypeMappingList
        self.assertEqual(result_content.count('@MqTypeMappingList'), 1)
    
    def test_create_new_mqtypemapping_when_none_exists(self):
        """Test creating new @MqTypeMappingList when file has none"""
        test_file = os.path.join(self.temp_dir, "Test.java")
        content = """package test;

@UsesMessageQueue
public class Test extends BaseTest {
}
"""
        with open(test_file, 'w') as f:
            f.write(content)
        
        issue = Issue(rule_name="Rule Test", severity="high", 
            file_path=test_file,
            line_number=3,
            rule=3,
            description="Missing PACKAGE_INSTALL mappings",
            fix_available=True
        )
        
        # Apply fix
        result = self.fixer._fix_rule3(issue, dry_run=False)
        self.assertTrue(result)
        
        # Read result
        with open(test_file, 'r') as f:
            result_content = f.read()
        
        # Verify new @MqTypeMappingList was created
        self.assertIn('@MqTypeMappingList({', result_content)
        self.assertIn('MessageQueueTypeEnum.PACKAGE_INSTALL', result_content)
        self.assertEqual(result_content.count('@MqTypeMappingList'), 1)
    
    def test_merge_countdown_latches(self):
        """Test merging countdown latches into existing list"""
        test_file = os.path.join(self.temp_dir, "Test.java")
        content = """package test;

import common.messaging.annotations.MqCustomCountDownLatch;
import common.messaging.annotations.MqCustomCountDownLatchList;

@MqCustomCountDownLatchList({
    @MqCustomCountDownLatch(timeout = 600, name = EXISTING_LATCH)
})
public class Test extends BaseTest {
}
"""
        with open(test_file, 'w') as f:
            f.write(content)
        
        issue = Issue(rule_name="Rule Test", severity="high", 
            file_path=test_file,
            line_number=6,
            rule=4,
            description="Missing countdown latches",
            fix_available=True
        )
        
        # Apply fix
        result = self.fixer._fix_rule4(issue, dry_run=False)
        self.assertTrue(result)
        
        # Read result
        with open(test_file, 'r') as f:
            result_content = f.read()
        
        # Verify new latches were added
        self.assertIn('CREATE_ARTIFACT_VERSION_PREPARING_ENDPOINT_LATCH', result_content)
        self.assertIn('BUILD_ARTIFACT_VERSION_DONE_LATCH', result_content)
        self.assertIn('PACKAGE2_METADATA_DEPLOY_LATCH', result_content)
        
        # Verify original latch is still there
        self.assertIn('EXISTING_LATCH', result_content)
        
        # Verify only one @MqCustomCountDownLatchList
        self.assertEqual(result_content.count('@MqCustomCountDownLatchList'), 1)
    
    def test_skip_if_already_has_package_install(self):
        """Test that we skip files that already have PACKAGE_INSTALL mappings"""
        test_file = os.path.join(self.temp_dir, "Test.java")
        content = """package test;

import com.force.packaging2.build.state.MetadataDeployQueueMessageTestHandler;

@MqTypeMappingList({
    @MqTypeMapping(type = MessageQueueTypeEnum.PACKAGE_INSTALL, handler = MetadataDeployQueueMessageTestHandler.class)
})
public class Test extends BaseTest {
}
"""
        with open(test_file, 'w') as f:
            f.write(content)
        
        issue = Issue(rule_name="Rule Test", severity="high", 
            file_path=test_file,
            line_number=5,
            rule=3,
            description="Missing PACKAGE_INSTALL mappings",
            fix_available=True
        )
        
        # Apply fix - should skip
        result = self.fixer._fix_rule3(issue, dry_run=False)
        self.assertFalse(result)
        
        # Read result - should be unchanged
        with open(test_file, 'r') as f:
            result_content = f.read()
        
        self.assertEqual(content, result_content)
    
    def test_multiline_annotation_with_complex_params(self):
        """Test handling multi-line annotation with complex parameters"""
        lines = [
            "@MqCustomCountDownLatchList({",
            "    @MqCustomCountDownLatch(timeout = TestHandler.TIMEOUT_SECONDS,",
            "                            name = TestHandler.COUNTDOWN_LATCH_NAME,",
            "                            initialCount = 1)",
            "})",
            "public class Test {",
        ]
        idx = self.fixer._find_closing_brace(lines, 0)
        self.assertEqual(idx, 4)
        self.assertIn('})', lines[idx])


class TestRuleFixes(unittest.TestCase):
    """Test individual rule fixes"""
    
    def setUp(self):
        self.fixer = TestDoctorFixer()
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_rule1_adds_register_new_org(self):
        """Test Rule 1: Adding registerNewOrg()"""
        test_file = os.path.join(self.temp_dir, "Test.java")
        content = """package test;

public class Test extends BaseTest {
    public void testMethod() throws Exception {
        ScratchOrgInfo soi = testUtil.createScratchOrg();
        // Missing registerNewOrg here
    }
}
"""
        with open(test_file, 'w') as f:
            f.write(content)
        
        issue = Issue(rule_name="Rule Test", severity="high", 
            file_path=test_file,
            line_number=5,
            rule=1,
            description="Missing registerNewOrg()",
            fix_available=True
        )
        
        result = self.fixer._fix_rule1(issue, dry_run=False)
        self.assertTrue(result)
        
        with open(test_file, 'r') as f:
            result_content = f.read()
        
        self.assertIn('getMessageQueueTestFramework().registerNewOrg', result_content)
    
    def test_rule2_adds_use_test_queue(self):
        """Test Rule 2: Adding USE_TEST_QUEUE"""
        test_file = os.path.join(self.temp_dir, "Test.java")
        content = """package test;

public class Test extends BaseTest {
    @Override
    protected void ftestSetUp() throws Exception {
        super.ftestSetUp();
        // Missing USE_TEST_QUEUE here
    }
}
"""
        with open(test_file, 'w') as f:
            f.write(content)
        
        issue = Issue(rule_name="Rule Test", severity="high", 
            file_path=test_file,
            line_number=5,
            rule=2,
            description="Missing USE_TEST_QUEUE",
            fix_available=True
        )
        
        result = self.fixer._fix_rule2(issue, dry_run=False)
        self.assertTrue(result)
        
        with open(test_file, 'r') as f:
            result_content = f.read()
        
        self.assertIn('USE_TEST_QUEUE', result_content)
        self.assertIn('TestContext.pushTestValue', result_content)


if __name__ == '__main__':
    unittest.main()
