"""Unit tests for cache_parser module."""

import pytest
from cache_parser import parse_nova_act_steps

# Nova Act box format: <box>top,left,bottom,right</box>
# Parsed to: x1=left, y1=top, x2=right, y2=bottom


class TestParseClick:
    """Tests for agentClick parsing."""
    
    def test_parse_single_click(self):
        """Parse single click action. <box>100,200,300,400</box> = top=100,left=200,bottom=300,right=400"""
        response = {
            'steps': [{
                'response': {
                    'rawProgramBody': 'think("clicking button");\nagentClick("<box>100,200,300,400</box>");\nreturn();'
                }
            }]
        }
        result = parse_nova_act_steps(response)
        assert result == [{
            'type': 'click',
            'bbox': {'x1': 200, 'y1': 100, 'x2': 400, 'y2': 300}
        }]
    
    def test_parse_click_with_quotes(self):
        """Parse click with quoted bbox. <box>621,71,640,143</box> = top=621,left=71,bottom=640,right=143"""
        response = {
            'steps': [{
                'response': {
                    'rawProgramBody': 'agentClick("<box>621,71,640,143</box>");'
                }
            }]
        }
        result = parse_nova_act_steps(response)
        assert result == [{
            'type': 'click',
            'bbox': {'x1': 71, 'y1': 621, 'x2': 143, 'y2': 640}
        }]


class TestParseHover:
    """Tests for agentHover parsing."""
    
    def test_parse_single_hover(self):
        """Parse single hover action. <box>100,200,150,250</box> = top=100,left=200,bottom=150,right=250"""
        response = {
            'steps': [{
                'response': {
                    'rawProgramBody': 'think("hovering");\nagentHover("<box>100,200,150,250</box>");\nreturn();'
                }
            }]
        }
        result = parse_nova_act_steps(response)
        assert result == [{
            'type': 'hover',
            'bbox': {'x1': 200, 'y1': 100, 'x2': 250, 'y2': 150}
        }]


class TestParseType:
    """Tests for agentType parsing."""
    
    def test_parse_type_without_enter(self):
        """Parse type action. <box>300,400,500,450</box> = top=300,left=400,bottom=500,right=450"""
        response = {
            'steps': [{
                'response': {
                    'rawProgramBody': 'agentType("admin", "<box>300,400,500,450</box>");'
                }
            }]
        }
        result = parse_nova_act_steps(response)
        assert result == [{
            'type': 'type',
            'text': 'admin',
            'bbox': {'x1': 400, 'y1': 300, 'x2': 450, 'y2': 500},
            'press_enter': False
        }]
    
    def test_parse_type_with_enter(self):
        """Parse type action with Enter. <box>100,100,400,150</box> = top=100,left=100,bottom=400,right=150"""
        response = {
            'steps': [{
                'response': {
                    'rawProgramBody': 'agentType("search query", "<box>100,100,400,150</box>", true);'
                }
            }]
        }
        result = parse_nova_act_steps(response)
        assert result == [{
            'type': 'type',
            'text': 'search query',
            'bbox': {'x1': 100, 'y1': 100, 'x2': 150, 'y2': 400},
            'press_enter': True
        }]
    
    def test_parse_type_with_false_enter(self):
        """Parse type action with explicit false for Enter."""
        response = {
            'steps': [{
                'response': {
                    'rawProgramBody': 'agentType("text", "<box>10,20,30,40</box>", false);'
                }
            }]
        }
        result = parse_nova_act_steps(response)
        assert result[0]['press_enter'] is False
    
    def test_parse_type_empty_string(self):
        """Parse type action with empty string."""
        response = {
            'steps': [{
                'response': {
                    'rawProgramBody': 'agentType("", "<box>10,20,30,40</box>");'
                }
            }]
        }
        result = parse_nova_act_steps(response)
        assert result[0]['text'] == ''


class TestParseScroll:
    """Tests for agentScroll parsing."""
    
    def test_parse_scroll_down_no_value(self):
        """Parse scroll down. <box>0,0,1920,1080</box> = top=0,left=0,bottom=1920,right=1080"""
        response = {
            'steps': [{
                'response': {
                    'rawProgramBody': 'agentScroll("down", "<box>0,0,1920,1080</box>");'
                }
            }]
        }
        result = parse_nova_act_steps(response)
        assert result == [{
            'type': 'scroll',
            'direction': 'down',
            'bbox': {'x1': 0, 'y1': 0, 'x2': 1080, 'y2': 1920},
            'value': None
        }]
    
    def test_parse_scroll_up_with_value(self):
        """Parse scroll up with explicit value."""
        response = {
            'steps': [{
                'response': {
                    'rawProgramBody': 'agentScroll("up", "<box>100,100,500,500</box>", 200.0);'
                }
            }]
        }
        result = parse_nova_act_steps(response)
        assert result[0]['value'] == 200.0
    
    def test_parse_scroll_all_directions(self):
        """Parse scroll in all directions."""
        for direction in ['up', 'down', 'left', 'right']:
            response = {
                'steps': [{
                    'response': {
                        'rawProgramBody': f'agentScroll("{direction}", "<box>0,0,100,100</box>");'
                    }
                }]
            }
            result = parse_nova_act_steps(response)
            assert result[0]['direction'] == direction


class TestParseNavigate:
    """Tests for goToUrl parsing."""
    
    def test_parse_navigate(self):
        """Parse navigate action."""
        response = {
            'steps': [{
                'response': {
                    'rawProgramBody': 'goToUrl("https://example.com/login");'
                }
            }]
        }
        result = parse_nova_act_steps(response)
        assert result == [{'type': 'navigate', 'url': 'https://example.com/login'}]
    
    def test_parse_navigate_complex_url(self):
        """Parse navigate with complex URL."""
        response = {
            'steps': [{
                'response': {
                    'rawProgramBody': 'goToUrl("https://example.com/path?param=value&other=123");'
                }
            }]
        }
        result = parse_nova_act_steps(response)
        assert result[0]['url'] == 'https://example.com/path?param=value&other=123'


class TestMultipleSteps:
    """Tests for multiple steps in response."""
    
    def test_parse_multiple_actions(self):
        """Parse response with multiple steps."""
        response = {
            'steps': [
                {'response': {'rawProgramBody': 'think("clicking");\nagentClick("<box>100,200,300,400</box>");'}},
                {'response': {'rawProgramBody': 'think("typing");\nagentType("text", "<box>10,20,30,40</box>");\nreturn();'}}
            ]
        }
        result = parse_nova_act_steps(response)
        assert len(result) == 2
        assert result[0]['type'] == 'click'
        assert result[1]['type'] == 'type'
    
    def test_parse_mixed_with_non_cacheable(self):
        """Parse response with cacheable and non-cacheable actions."""
        response = {
            'steps': [
                {'response': {'rawProgramBody': 'think("analyzing page");'}},
                {'response': {'rawProgramBody': 'agentClick("<box>100,200,300,400</box>");'}},
                {'response': {'rawProgramBody': 'return();'}}
            ]
        }
        result = parse_nova_act_steps(response)
        assert len(result) == 1
        assert result[0]['type'] == 'click'


class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_empty_steps_array(self):
        result = parse_nova_act_steps({'steps': []})
        assert result is None
    
    def test_missing_steps_field(self):
        result = parse_nova_act_steps({})
        assert result is None
    
    def test_missing_raw_program_body(self):
        result = parse_nova_act_steps({'steps': [{'response': {}}]})
        assert result is None
    
    def test_only_non_cacheable_actions(self):
        response = {
            'steps': [
                {'response': {'rawProgramBody': 'think("analyzing");'}},
                {'response': {'rawProgramBody': 'return();'}},
                {'response': {'rawProgramBody': 'wait(2);'}},
                {'response': {'rawProgramBody': 'takeObservation();'}}
            ]
        }
        assert parse_nova_act_steps(response) is None
    
    def test_malformed_bbox_coordinates(self):
        response = {'steps': [{'response': {'rawProgramBody': 'agentClick("<box>abc,def,ghi,jkl</box>");'}}]}
        assert parse_nova_act_steps(response) is None
    
    def test_none_input(self):
        assert parse_nova_act_steps(None) is None
    
    def test_missing_response_field(self):
        assert parse_nova_act_steps({'steps': [{'other_field': 'value'}]}) is None


class TestRealWorldScenario:
    """Tests based on real Nova Act responses."""
    
    def test_close_popup_scenario(self):
        """<box>621,71,640,143</box> = top=621,left=71,bottom=640,right=143"""
        response = {
            'steps': [
                {'response': {'rawProgramBody': 'think("Looking for popup close button");\nagentClick("<box>621,71,640,143</box>");'}},
                {'response': {'rawProgramBody': 'think("Popup closed successfully");\nreturn();'}}
            ],
            'metadata': {'num_steps_executed': 2}
        }
        result = parse_nova_act_steps(response)
        assert len(result) == 1
        assert result[0] == {
            'type': 'click',
            'bbox': {'x1': 71, 'y1': 621, 'x2': 143, 'y2': 640}
        }
    
    def test_login_scenario(self):
        """Test login with username and password."""
        response = {
            'steps': [
                {'response': {'rawProgramBody': 'agentType("admin", "<box>300,400,500,450</box>");'}},
                {'response': {'rawProgramBody': 'agentType("password123", "<box>300,500,500,550</box>", true);'}}
            ]
        }
        result = parse_nova_act_steps(response)
        assert len(result) == 2
        assert result[0]['text'] == 'admin'
        assert result[0]['press_enter'] is False
        assert result[1]['text'] == 'password123'
        assert result[1]['press_enter'] is True
