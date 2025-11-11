#!/usr/bin/env python3
"""
TestDoctor - Automated Test Fixer for 2GP Packaging Tests

Detects and fixes common anti-patterns in 2GP packaging functional tests that cause
timeouts and flaky test failures in autobuilds.

Diagnoses and heals test issues related to:
- Message queue registration
- Test queue usage
- Package install mappings  
- Countdown latch synchronization
"""
import json
import glob
import re
import os
from pathlib import Path
from typing import List, Dict, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime

@dataclass
class Issue:
    """Represents a test issue"""
    file_path: str
    rule: int
    rule_name: str
    description: str
    severity: str
    line_number: int = 0
    fix_available: bool = True

class TestDoctorScanner:
    """Scans test files for anti-patterns"""
    
    def __init__(self, test_dir: str):
        self.test_dir = test_dir
        self.issues: List[Issue] = []
        
    def scan_all(self) -> List[Issue]:
        """Scan all test files for all rules"""
        print(f"🔍 Scanning tests in: {self.test_dir}")
        
        test_files = glob.glob(f"{self.test_dir}/**/*Test.java", recursive=True)
        print(f"📁 Found {len(test_files)} test files")
        
        for file_path in test_files:
            self.scan_file(file_path)
        
        return self.issues
    
    def scan_file(self, file_path: str):
        """Scan a single file for all rules"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
            
            # Rule 1: Missing registerNewOrg()
            if self._has_scratch_org_creation(content) and not self._has_register_org(content):
                self.issues.append(Issue(
                    file_path=file_path,
                    rule=1,
                    rule_name="Missing registerNewOrg()",
                    description="Test creates scratch orgs but doesn't register them with message queue framework",
                    severity="HIGH",
                    line_number=self._find_line_number(lines, 'createScratchOrg')
                ))
            
            # Rule 2: Missing USE_TEST_QUEUE
            if (self._extends_base_test(content) and 
                self._has_package_operations(content) and 
                not self._has_use_test_queue(content)):
                self.issues.append(Issue(
                    file_path=file_path,
                    rule=2,
                    rule_name="Missing USE_TEST_QUEUE",
                    description="Test extends BaseTest and does package operations but doesn't use test queues",
                    severity="HIGH",
                    line_number=self._find_line_number(lines, 'extends BaseTest')
                ))
            
            # Rule 3: Missing PACKAGE_INSTALL mappings
            if (self._has_uses_message_queue(content) and 
                self._has_install_operations(content) and 
                not self._has_package_install_mapping(content) and
                not self._uses_method_level_annotations(lines, '@MqTypeMappingList')):
                self.issues.append(Issue(
                    file_path=file_path,
                    rule=3,
                    rule_name="Missing PACKAGE_INSTALL mappings",
                    description="Test installs packages but missing @MqTypeMapping for PACKAGE_INSTALL",
                    severity="MEDIUM",
                    line_number=self._find_line_number(lines, '@UsesMessageQueue')
                ))
            
            # Rule 4: Missing countdown latches
            if (self._has_uses_message_queue(content) and 
                self._creates_package_versions(content) and 
                not self._has_countdown_latches(content) and
                not self._uses_method_level_annotations(lines, '@MqCustomCountDownLatchList')):
                self.issues.append(Issue(
                    file_path=file_path,
                    rule=4,
                    rule_name="Missing countdown latches",
                    description="Test creates package versions but missing required countdown latches",
                    severity="MEDIUM",
                    line_number=self._find_line_number(lines, 'createPackage2Version')
                ))
                
        except Exception as e:
            print(f"⚠️  Error scanning {file_path}: {e}")
    
    # Detection helpers
    def _has_scratch_org_creation(self, content: str) -> bool:
        return 'createScratchOrg' in content or 'reestablishRequest.*Subscriber' in content
    
    def _has_register_org(self, content: str) -> bool:
        return 'registerNewOrg' in content
    
    def _extends_base_test(self, content: str) -> bool:
        return re.search(r'extends\s+BaseTest\s', content) is not None
    
    def _has_package_operations(self, content: str) -> bool:
        patterns = ['createPackage2Version', 'convertPackage', 'installPackage', 'createInstallRequest']
        return any(p in content for p in patterns)
    
    def _has_use_test_queue(self, content: str) -> bool:
        return 'USE_TEST_QUEUE' in content or 'extends BaseBuildOrgTest' in content
    
    def _has_uses_message_queue(self, content: str) -> bool:
        return '@UsesMessageQueue' in content
    
    def _has_install_operations(self, content: str) -> bool:
        patterns = ['installPackage', 'createInstallRequest', 'install(']
        return any(p in content for p in patterns)
    
    def _has_package_install_mapping(self, content: str) -> bool:
        return 'PACKAGE_INSTALL' in content
    
    def _creates_package_versions(self, content: str) -> bool:
        patterns = ['createPackage2Version', 'convertPackage', 'TestPackage2VersionBuilder']
        return any(p in content for p in patterns)
    
    def _has_countdown_latches(self, content: str) -> bool:
        return 'CREATE_ARTIFACT_VERSION_PREPARING_ENDPOINT_LATCH' in content or 'BUILD_ARTIFACT_VERSION_DONE_LATCH' in content
    
    def _uses_method_level_annotations(self, lines: List[str], annotation: str) -> bool:
        """Check if file uses method-level annotations instead of class-level"""
        # Find class declaration
        class_line_idx = None
        for i, line in enumerate(lines):
            if re.search(r'public\s+class\s+\w+.*Test', line):
                class_line_idx = i
                break
        
        if class_line_idx is None:
            return False
        
        # Check if there's an annotation before the class
        has_class_level = False
        for i in range(max(0, class_line_idx - 10), class_line_idx):
            if annotation in lines[i]:
                has_class_level = True
                break
        
        # If no class-level annotation but file has the annotation somewhere, it's method-level
        content = '\n'.join(lines)
        return not has_class_level and annotation in content
    
    def _find_line_number(self, lines: List[str], pattern: str) -> int:
        """Find the line number where pattern appears"""
        for i, line in enumerate(lines, 1):
            if pattern in line:
                return i
        return 0

class TestDoctorFixer:
    """Fixes issues automatically"""
    
    def __init__(self):
        self.fixes_applied = 0
    
    def _find_annotation_list(self, lines: List[str], annotation: str) -> int:
        """Find the line index where an annotation list starts (e.g., @MqTypeMappingList)"""
        for i, line in enumerate(lines):
            if annotation in line and '{' in line:
                return i
        return None
    
    def _find_closing_brace(self, lines: List[str], start_idx: int) -> int:
        """Find the closing brace }) for an annotation list starting at start_idx"""
        brace_count = 0
        in_string = False
        escape_next = False
        
        for i in range(start_idx, len(lines)):
            line = lines[i]
            for char in line:
                # Handle string literals to avoid counting braces inside strings
                if escape_next:
                    escape_next = False
                    continue
                if char == '\\':
                    escape_next = True
                    continue
                if char == '"':
                    in_string = not in_string
                    continue
                    
                if not in_string:
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        # Found the matching closing brace
                        if brace_count == 0:
                            return i
        return None
    
    def _add_imports(self, lines: List[str], imports_to_add: List[str]) -> List[str]:
        """Helper to add imports to the file"""
        new_lines = []
        imports_added = False
        for line in lines:
            # Add imports after the first existing import
            if not imports_added and line.startswith('import '):
                for imp in imports_to_add:
                    new_lines.append(imp)
                imports_added = True
            new_lines.append(line)
        return new_lines
    
    def fix_issue(self, issue: Issue, dry_run: bool = False) -> bool:
        """Fix a single issue"""
        if not issue.fix_available:
            return False
        
        try:
            if issue.rule == 1:
                return self._fix_rule1(issue, dry_run)
            elif issue.rule == 2:
                return self._fix_rule2(issue, dry_run)
            elif issue.rule == 3:
                return self._fix_rule3(issue, dry_run)
            elif issue.rule == 4:
                return self._fix_rule4(issue, dry_run)
        except Exception as e:
            print(f"❌ Error fixing {issue.file_path}: {e}")
            return False
        
        return False
    
    def _fix_rule1(self, issue: Issue, dry_run: bool) -> bool:
        """Add registerNewOrg() calls"""
        with open(issue.file_path, 'r') as f:
            lines = f.readlines()
        
        new_lines = []
        for i, line in enumerate(lines):
            new_lines.append(line)
            # Add registerNewOrg after createScratchOrg
            if 'createScratchOrg' in line and i + 1 < len(lines):
                # Check if next line already has registerNewOrg - skip if it does
                if i + 1 < len(lines) and 'registerNewOrg' in lines[i + 1]:
                    continue
                
                # Extract variable name from the line
                # Pattern: ScratchOrgInfo varName = ...createScratchOrg(...)
                var_match = re.search(r'(\w+)\s*=.*createScratchOrg', line)
                var_name = var_match.group(1) if var_match else 'scratchOrgInfo'
                
                # Get indentation
                indent = len(line) - len(line.lstrip())
                # Add the fix with correct variable name
                new_lines.append(' ' * indent + f'getMessageQueueTestFramework().registerNewOrg({var_name}.getScratchOrgId());\n')
                self.fixes_applied += 1
        
        if not dry_run:
            with open(issue.file_path, 'w') as f:
                f.writelines(new_lines)
        
        return True
    
    def _fix_rule2(self, issue: Issue, dry_run: bool) -> bool:
        """Add USE_TEST_QUEUE setting"""
        with open(issue.file_path, 'r') as f:
            content = f.read()
            lines = content.split('\n')
        
        # Check if USE_TEST_QUEUE already exists
        if 'USE_TEST_QUEUE' in content:
            return False
        
        # Add required imports if missing
        needs_imports = []
        if 'import system.context.TestContext;' not in content:
            needs_imports.append('import system.context.TestContext;')
        # Check for both old and new import paths
        if 'AqSpecificOptions' not in content:
            needs_imports.append('import common.messaging.AqSpecificOptions;')
        if 'import system.context.UserContext;' not in content:
            needs_imports.append('import system.context.UserContext;')
        
        # Find ftestSetUp method and add USE_TEST_QUEUE
        new_lines = []
        added = False
        imports_added = False
        for i, line in enumerate(lines):
            # Add imports after package declaration
            if not imports_added and needs_imports and line.startswith('import '):
                for imp in needs_imports:
                    new_lines.append(imp)
                needs_imports = []
                imports_added = True
            
            new_lines.append(line)
            if not added and ('protected void ftestSetUp()' in line or 'public void ftestSetUp()' in line):
                # Find the super.ftestSetUp() call
                for j in range(i + 1, min(i + 10, len(lines))):
                    if 'super.ftestSetUp()' in lines[j]:
                        indent = len(lines[j]) - len(lines[j].lstrip())
                        new_lines.append('')
                        new_lines.append(' ' * indent + 'TestContext.pushTestValue(UserContext.get().getUserId(), AqSpecificOptions.USE_TEST_QUEUE, true, null);')
                        self.fixes_applied += 1
                        added = True
                        break
        
        if not dry_run and added:
            with open(issue.file_path, 'w') as f:
                f.write('\n'.join(new_lines))
        
        return added
    
    def _fix_rule3(self, issue: Issue, dry_run: bool) -> bool:
        """Add PACKAGE_INSTALL MQ mappings"""
        with open(issue.file_path, 'r') as f:
            content = f.read()
            lines = content.split('\n')
        
        # Check if PACKAGE_INSTALL mapping already exists with proper handler
        has_package_install = 'MessageQueueTypeEnum.PACKAGE_INSTALL' in content and 'MetadataDeployQueueMessageTestHandler' in content
        
        # Only skip if the file already has PACKAGE_INSTALL mappings
        if has_package_install:
            return False
        
        # Skip if file uses method-level annotations - check if class has no annotations but methods do
        class_line_idx = None
        for i, line in enumerate(lines):
            if re.search(r'public\s+class\s+\w+.*Test', line):
                class_line_idx = i
                break
        
        if class_line_idx is not None:
            # Check if there's an @MqTypeMappingList before the class
            has_class_level = False
            for i in range(max(0, class_line_idx - 10), class_line_idx):
                if '@MqTypeMappingList' in lines[i]:
                    has_class_level = True
                    break
            
            # If no class-level annotation but file has method-level ones, skip
            if not has_class_level and '@MqTypeMappingList' in content:
                return False
        
        # Add required imports if missing
        needs_imports = []
        if 'import common.messaging.annotations.MqTypeMapping;' not in content:
            needs_imports.append('import common.messaging.annotations.MqTypeMapping;')
        if 'import common.messaging.annotations.MqTypeMappingList;' not in content:
            needs_imports.append('import common.messaging.annotations.MqTypeMappingList;')
        if 'import common.udd.constants.messaging.MessageQueueTypeEnum;' not in content:
            needs_imports.append('import common.udd.constants.messaging.MessageQueueTypeEnum;')
        if 'import com.force.packaging2.build.state.MetadataDeployQueueMessageTestHandler;' not in content:
            needs_imports.append('import com.force.packaging2.build.state.MetadataDeployQueueMessageTestHandler;')
        
        # Add imports first
        if needs_imports:
            lines = self._add_imports(lines, needs_imports)
        
        # Check if there's an existing @MqTypeMappingList to merge into
        existing_list_idx = self._find_annotation_list(lines, '@MqTypeMappingList')
        
        new_lines = []
        added = False
        
        if existing_list_idx is not None:
            # Merge into existing @MqTypeMappingList
            closing_idx = self._find_closing_brace(lines, existing_list_idx)
            if closing_idx is not None:
                for i, line in enumerate(lines):
                    if i == closing_idx:
                        # Add comma to previous line if it doesn't have one
                        if new_lines and not new_lines[-1].rstrip().endswith(',') and not new_lines[-1].rstrip().endswith('{'):
                            new_lines[-1] = new_lines[-1].rstrip() + ','
                        # Insert new mappings before the closing brace
                        indent = len(line) - len(line.lstrip())
                        annotations = [
                            '    @MqTypeMapping(type = MessageQueueTypeEnum.PACKAGE_INSTALL, handler = MetadataDeployQueueMessageTestHandler.class),',
                            '    @MqTypeMapping(type = MessageQueueTypeEnum.PACKAGE_INSTALL_DEFAULT, handler = MetadataDeployQueueMessageTestHandler.class),',
                            '    @MqTypeMapping(type = MessageQueueTypeEnum.PACKAGE_INSTALL_SMALL, handler = MetadataDeployQueueMessageTestHandler.class),',
                            '    @MqTypeMapping(type = MessageQueueTypeEnum.PACKAGE_INSTALL_LARGE, handler = MetadataDeployQueueMessageTestHandler.class),'
                        ]
                        for annotation in annotations:
                            new_lines.append(' ' * indent + annotation)
                        self.fixes_applied += 1
                        added = True
                    new_lines.append(line)
        else:
            # Create new @MqTypeMappingList before class declaration
            for i, line in enumerate(lines):
                # Look for class declaration
                if not added and re.search(r'public\s+class\s+\w+.*Test', line):
                    indent = len(line) - len(line.lstrip())
                    # Use @MqTypeMappingList wrapper for multiple annotations
                    new_lines.append(' ' * indent + '@MqTypeMappingList({')
                    annotations = [
                        '    @MqTypeMapping(type = MessageQueueTypeEnum.PACKAGE_INSTALL, handler = MetadataDeployQueueMessageTestHandler.class),',
                        '    @MqTypeMapping(type = MessageQueueTypeEnum.PACKAGE_INSTALL_DEFAULT, handler = MetadataDeployQueueMessageTestHandler.class),',
                        '    @MqTypeMapping(type = MessageQueueTypeEnum.PACKAGE_INSTALL_SMALL, handler = MetadataDeployQueueMessageTestHandler.class),',
                        '    @MqTypeMapping(type = MessageQueueTypeEnum.PACKAGE_INSTALL_LARGE, handler = MetadataDeployQueueMessageTestHandler.class)'
                    ]
                    for annotation in annotations:
                        new_lines.append(' ' * indent + annotation)
                    new_lines.append(' ' * indent + '})')
                    self.fixes_applied += 1
                    added = True
                
                new_lines.append(line)
        
        if not dry_run and added:
            with open(issue.file_path, 'w') as f:
                f.write('\n'.join(new_lines))
        
        return added
    
    def _fix_rule4(self, issue: Issue, dry_run: bool) -> bool:
        """Add countdown latches"""
        with open(issue.file_path, 'r') as f:
            content = f.read()
            lines = content.split('\n')
        
        # Check if countdown latches already exist with all three required handlers
        has_create = 'CreateArtifactVersionTestHandler.CREATE_ARTIFACT_VERSION_PREPARING_ENDPOINT_LATCH' in content
        has_build = 'BuildArtifactVersionTestHandler.BUILD_ARTIFACT_VERSION_DONE_LATCH' in content
        has_deploy = 'MetadataDeployQueueMessageTestHandler.PACKAGE2_METADATA_DEPLOY_LATCH' in content
        
        # Only skip if all three are present
        if has_create and has_build and has_deploy:
            return False
        
        # Skip if file uses method-level annotations - check if class has no annotations but methods do
        class_line_idx = None
        for i, line in enumerate(lines):
            if re.search(r'public\s+class\s+\w+.*Test', line):
                class_line_idx = i
                break
        
        if class_line_idx is not None:
            # Check if there's an @MqCustomCountDownLatchList before the class
            has_class_level = False
            for i in range(max(0, class_line_idx - 10), class_line_idx):
                if '@MqCustomCountDownLatchList' in lines[i]:
                    has_class_level = True
                    break
            
            # If no class-level annotation but file has method-level ones, skip
            if not has_class_level and '@MqCustomCountDownLatchList' in content:
                return False
        
        # Add required imports if missing
        needs_imports = []
        if 'import common.messaging.annotations.MqCustomCountDownLatch;' not in content:
            needs_imports.append('import common.messaging.annotations.MqCustomCountDownLatch;')
        if 'import common.messaging.annotations.MqCustomCountDownLatchList;' not in content:
            needs_imports.append('import common.messaging.annotations.MqCustomCountDownLatchList;')
        # Use the correct shorter import paths that most tests use
        if 'CreateArtifactVersionTestHandler' not in content:
            needs_imports.append('import com.force.packaging2.CreateArtifactVersionTestHandler;')
        if 'BuildArtifactVersionTestHandler' not in content:
            needs_imports.append('import com.force.packaging2.BuildArtifactVersionTestHandler;')
        if 'MetadataDeployQueueMessageTestHandler' not in content:
            needs_imports.append('import com.force.packaging2.build.state.MetadataDeployQueueMessageTestHandler;')
        
        # Add imports first
        if needs_imports:
            lines = self._add_imports(lines, needs_imports)
        
        # Check if there's an existing @MqCustomCountDownLatchList to merge into
        existing_list_idx = self._find_annotation_list(lines, '@MqCustomCountDownLatchList')
        
        new_lines = []
        added = False
        
        if existing_list_idx is not None:
            # Merge into existing @MqCustomCountDownLatchList
            closing_idx = self._find_closing_brace(lines, existing_list_idx)
            if closing_idx is not None:
                for i, line in enumerate(lines):
                    if i == closing_idx:
                        # Add comma to previous line if it doesn't have one
                        if new_lines and not new_lines[-1].rstrip().endswith(',') and not new_lines[-1].rstrip().endswith('{'):
                            new_lines[-1] = new_lines[-1].rstrip() + ','
                        # Insert new latches before the closing brace
                        indent = len(line) - len(line.lstrip())
                        annotations = [
                            '    @MqCustomCountDownLatch(name = CreateArtifactVersionTestHandler.CREATE_ARTIFACT_VERSION_PREPARING_ENDPOINT_LATCH, timeout = 600),',
                            '    @MqCustomCountDownLatch(name = BuildArtifactVersionTestHandler.BUILD_ARTIFACT_VERSION_DONE_LATCH, timeout = 600),',
                            '    @MqCustomCountDownLatch(name = MetadataDeployQueueMessageTestHandler.PACKAGE2_METADATA_DEPLOY_LATCH, timeout = 600),'
                        ]
                        for annotation in annotations:
                            new_lines.append(' ' * indent + annotation)
                        self.fixes_applied += 1
                        added = True
                    new_lines.append(line)
        else:
            # Create new @MqCustomCountDownLatchList before class declaration
            for i, line in enumerate(lines):
                # Look for class declaration
                if not added and re.search(r'public\s+class\s+\w+.*Test', line):
                    indent = len(line) - len(line.lstrip())
                    # Use @MqCustomCountDownLatchList wrapper for multiple annotations
                    new_lines.append(' ' * indent + '@MqCustomCountDownLatchList({')
                    annotations = [
                        '    @MqCustomCountDownLatch(name = CreateArtifactVersionTestHandler.CREATE_ARTIFACT_VERSION_PREPARING_ENDPOINT_LATCH, timeout = 600),',
                        '    @MqCustomCountDownLatch(name = BuildArtifactVersionTestHandler.BUILD_ARTIFACT_VERSION_DONE_LATCH, timeout = 600),',
                        '    @MqCustomCountDownLatch(name = MetadataDeployQueueMessageTestHandler.PACKAGE2_METADATA_DEPLOY_LATCH, timeout = 600)'
                    ]
                    for annotation in annotations:
                        new_lines.append(' ' * indent + annotation)
                    new_lines.append(' ' * indent + '})')
                    self.fixes_applied += 1
                    added = True
                
                new_lines.append(line)
        
        if not dry_run and added:
            with open(issue.file_path, 'w') as f:
                f.write('\n'.join(new_lines))
        
        return added

class TestDoctorReporter:
    """Generates reports"""
    
    def __init__(self, issues: List[Issue]):
        self.issues = issues
    
    def print_summary(self):
        """Print summary to console"""
        print("\n" + "="*80)
        print("📊 TESTGUARD SCAN RESULTS")
        print("="*80)
        
        if not self.issues:
            print("✅ No issues found! All tests look good.")
            return
        
        # Group by rule
        by_rule = {}
        for issue in self.issues:
            if issue.rule not in by_rule:
                by_rule[issue.rule] = []
            by_rule[issue.rule].append(issue)
        
        print(f"\n🔴 Found {len(self.issues)} issues across {len(by_rule)} rules:\n")
        
        for rule_num in sorted(by_rule.keys()):
            issues = by_rule[rule_num]
            print(f"Rule {rule_num}: {issues[0].rule_name} - {len(issues)} files")
            for issue in issues[:5]:  # Show first 5
                filename = os.path.basename(issue.file_path)
                print(f"  • {filename}")
            if len(issues) > 5:
                print(f"  ... and {len(issues) - 5} more")
            print()
        
        print("="*80)
        print(f"💡 Run 'python3 testdoctor.py fix --all --auto' to fix automatically")
        print("="*80 + "\n")
    
    def generate_json(self, output_file: str = "testdoctor-report.json"):
        """Generate JSON report"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "total_issues": len(self.issues),
            "issues": [asdict(issue) for issue in self.issues]
        }
        
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"📄 JSON report saved to: {output_file}")
    
    def generate_html(self, output_file: str = "testdoctor-report.html"):
        """Generate HTML report"""
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>TestDoctor Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
        h1 {{ color: #333; }}
        .summary {{ background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
        .rule {{ background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
        .rule h2 {{ color: #d32f2f; }}
        .issue {{ background: #f9f9f9; padding: 10px; margin: 10px 0; border-left: 4px solid #d32f2f; }}
        .high {{ border-left-color: #d32f2f; }}
        .medium {{ border-left-color: #ff9800; }}
        .low {{ border-left-color: #4caf50; }}
    </style>
</head>
<body>
    <h1>🛡️ TestDoctor Report</h1>
    <div class="summary">
        <h2>Summary</h2>
        <p><strong>Total Issues:</strong> {len(self.issues)}</p>
        <p><strong>Scan Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
"""
        
        # Group by rule
        by_rule = {}
        for issue in self.issues:
            if issue.rule not in by_rule:
                by_rule[issue.rule] = []
            by_rule[issue.rule].append(issue)
        
        for rule_num in sorted(by_rule.keys()):
            issues = by_rule[rule_num]
            html += f"""
    <div class="rule">
        <h2>Rule {rule_num}: {issues[0].rule_name}</h2>
        <p>{issues[0].description}</p>
        <p><strong>Files affected:</strong> {len(issues)}</p>
"""
            for issue in issues:
                html += f"""
        <div class="issue {issue.severity.lower()}">
            <strong>{os.path.basename(issue.file_path)}</strong><br>
            <small>Line {issue.line_number} | Severity: {issue.severity}</small>
        </div>
"""
            html += "    </div>\n"
        
        html += """
</body>
</html>
"""
        
        with open(output_file, 'w') as f:
            f.write(html)
        
        print(f"📄 HTML report saved to: {output_file}")

def main():
    """Main CLI entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='2GPTestDoctor - Automated Test Fixer for 2GP Packaging Tests')
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Scan command
    scan_parser = subparsers.add_parser('scan', help='Scan tests for issues')
    scan_parser.add_argument('--path', required=True, help='Path to test directory')
    
    # Report command
    report_parser = subparsers.add_parser('report', help='Generate reports')
    report_parser.add_argument('--format', choices=['json', 'html', 'both'], default='both')
    
    # Fix command
    fix_parser = subparsers.add_parser('fix', help='Fix issues automatically')
    fix_parser.add_argument('--rule', type=int, choices=[1, 2, 3, 4], help='Fix specific rule')
    fix_parser.add_argument('--all', action='store_true', help='Fix all rules')
    fix_parser.add_argument('--auto', action='store_true', help='Apply fixes automatically')
    fix_parser.add_argument('--dry-run', action='store_true', help='Show what would be fixed')
    
    args = parser.parse_args()
    
    if args.command == 'scan':
        scanner = TestDoctorScanner(args.path)
        issues = scanner.scan_all()
        
        reporter = TestDoctorReporter(issues)
        reporter.print_summary()
        reporter.generate_json()
        reporter.generate_html()
        
    elif args.command == 'report':
        # Load from JSON
        try:
            with open('testdoctor-report.json', 'r') as f:
                data = json.load(f)
                issues = [Issue(**i) for i in data['issues']]
                reporter = TestDoctorReporter(issues)
                
                if args.format in ['json', 'both']:
                    reporter.generate_json()
                if args.format in ['html', 'both']:
                    reporter.generate_html()
        except FileNotFoundError:
            print("❌ No scan results found. Run 'scan' first.")
    
    elif args.command == 'fix':
        # Load issues
        try:
            with open('testdoctor-report.json', 'r') as f:
                data = json.load(f)
                issues = [Issue(**i) for i in data['issues']]
        except FileNotFoundError:
            print("❌ No scan results found. Run 'scan' first.")
            return
        
        fixer = TestDoctorFixer()
        
        # Filter by rule if specified
        if args.rule:
            issues = [i for i in issues if i.rule == args.rule]
        
        if not args.auto and not args.dry_run:
            print("⚠️  Use --auto to apply fixes or --dry-run to preview")
            return
        
        print(f"🔧 Fixing {len(issues)} issues...")
        
        for issue in issues:
            if fixer.fix_issue(issue, dry_run=args.dry_run):
                status = "Would fix" if args.dry_run else "Fixed"
                print(f"✓ {status}: {os.path.basename(issue.file_path)} (Rule {issue.rule})")
        
        print(f"\n✅ Applied {fixer.fixes_applied} fixes")
    
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
