# Nova Act Agent Actions Reference

Complete list of agent actions from Nova Act SDK.

**Source**: https://github.com/aws/nova-act/blob/main/src/nova_act/tools/browser/interface/browser.py

## Actions to Cache (5 total)

These actions modify the browser state and should be cached:

### 1. agentClick
```python
agentClick(box: str, click_type?: ClickType, click_options?: ClickOptions)
```
Clicks the center of the specified box.

**Example in rawProgramBody**:
```javascript
agentClick("<box>621,71,640,143</box>");
```

**Cached format**:
```python
{
    "type": "click",
    "bbox": {"x1": 621, "y1": 71, "x2": 640, "y2": 143}
}
```

### 2. agentHover
```python
agentHover(box: str)
```
Hovers on the center of the specified box.

**Example in rawProgramBody**:
```javascript
agentHover("<box>100,200,150,250</box>");
```

**Cached format**:
```python
{
    "type": "hover",
    "bbox": {"x1": 100, "y1": 200, "x2": 150, "y2": 250}
}
```

### 3. agentScroll
```python
agentScroll(direction: ScrollDirection, box: str, value?: float)
```
Scrolls the element in the specified box. Valid directions: up, down, left, right.

**Example in rawProgramBody**:
```javascript
agentScroll("down", "<box>0,0,1920,1080</box>");
agentScroll("up", "<box>100,100,500,500</box>", 200.0);
```

**Cached format**:
```python
{
    "type": "scroll",
    "direction": "down",
    "bbox": {"x1": 0, "y1": 0, "x2": 1920, "y2": 1080},
    "value": None  # or float
}
```

### 4. agentType
```python
agentType(value: str, box: str, pressEnter: bool = False)
```
Types the specified value into the element at the center of the box.

**Example in rawProgramBody**:
```javascript
agentType("admin", "<box>300,400,500,450</box>");
agentType("search query", "<box>100,100,400,150</box>", true);
```

**Cached format**:
```python
{
    "type": "type",
    "text": "admin",
    "bbox": {"x1": 300, "y1": 400, "x2": 500, "y2": 450},
    "press_enter": False
}
```

### 5. goToUrl
```python
goToUrl(url: str)
```
Navigates to the specified URL.

**Example in rawProgramBody**:
```javascript
goToUrl("https://example.com/login");
```

**Cached format**:
```python
{
    "type": "navigate",
    "url": "https://example.com/login"
}
```

## Actions NOT to Cache (6 total)

These actions don't modify browser state or shouldn't be cached:

### 6. think
```python
think(value: str)
```
Has no effect on the environment. Used for reasoning about the next action.

**Skip during parsing** - doesn't affect browser state.

### 7. return
```python
return(value?: str)
```
Complete execution of the task and return to the user.

**Skip during parsing** - marks end of execution.

### 8. throw
```python
throw(value: str)
```
Used when the task requested by the user is not possible.

**Skip during parsing** - error condition.

### 9. wait
```python
wait(seconds: float)
```
Pauses execution for the specified number of seconds.

**Skip during parsing** - timing-dependent, may not be needed in cache replay.

### 10. waitForPageToSettle
```python
waitForPageToSettle()
```
Ensure the browser page is ready for the next action.

**Skip during parsing** - Playwright handles this automatically.

### 11. takeObservation
```python
takeObservation() -> BrowserObservation
```
Take an observation of the existing browser state.

**Skip during parsing** - observation action, not a browser modification.

## Implementation Notes

### Bounding Box Format
All actions use `<box>x1,y1,x2,y2</box>` format where:
- `x1, y1` = top-left corner coordinates
- `x2, y2` = bottom-right corner coordinates

To execute, calculate center point:
```python
x = (x1 + x2) / 2
y = (y1 + y2) / 2
```

### Parsing Strategy
1. Parse `rawProgramBody` field from each step
2. Use regex to extract action name and parameters
3. Skip `think()`, `return()`, `throw()`, `wait*()`, `takeObservation()`
4. Cache only the 5 browser-modifying actions
5. Store as structured data (not raw code)

### Execution Strategy
Use Playwright API directly via `nova.page`:
- `agentClick` → `nova.page.mouse.click(x, y)`
- `agentHover` → `nova.page.mouse.move(x, y)`
- `agentType` → `nova.page.keyboard.type(text)` + optional `nova.page.keyboard.press("Enter")`
- `agentScroll` → `nova.page.evaluate("window.scrollBy(...)")`
- `goToUrl` → `nova.page.goto(url)`
