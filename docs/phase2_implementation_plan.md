# Last-Show Oracle: Phase 2 Implementation Plan
## Production Hardening + Date Parsing Fix

**Status**: Ready for Implementation  
**Priority**: High - Production Readiness  
**Estimated Effort**: 2-3 days  

---

## 🎯 **OVERVIEW**

Phase 2 combines **critical date parsing fixes** with **production hardening improvements** to create a bulletproof, production-ready Last-Show Oracle service. This phase addresses the identified date parsing issue (Proxima Parada "1901 Union St" → "1901-08-29") while implementing robust HTTP client behavior, enhanced logging, and comprehensive testing.

---

## 🚨 **PHASE 2A: CRITICAL DATE PARSING FIX (IMMEDIATE)**

### **Problem Identified**
- **Current Issue**: Regex `r'(\d{4}-\d{2}-\d{2})'` matches street addresses like "1901 Union St" as "1901-08-29"
- **Affected Artist**: Proxima Parada (confirmed in smoke test)
- **Root Cause**: Date parsing lacks context validation and intelligent pattern matching

### **Solution Strategy**
1. **Improve regex patterns** to look for date-like contexts
2. **Add validation** that dates appear in date-like patterns (e.g., after "on", "at", "playing", etc.)
3. **Enhance date sanity validation** to be more strict about what gets through

### **Code Changes Required**

#### **Enhanced `parse_date()` Function**
```python
def parse_date(date_text: str) -> Optional[str]:
    """Parse various date formats to ISO string with improved context validation."""
    if not date_text:
        return None
    
    # Look for ISO date in datetime attribute first (most reliable)
    iso_match = re.search(r'(\d{4}-\d{2}-\d{2})', date_text)
    if iso_match:
        return iso_match.group(1)
    
    # Look for dates in date-like contexts (more intelligent)
    date_patterns = [
        # Date after common date words
        r'(?:on|at|playing|performed|shows?|concert|date)\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        # Date in common formats
        r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        # ISO-like pattern but only in date contexts
        r'(?:date|time|on|at)\s+(\d{4}-\d{2}-\d{2})',
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, date_text, re.IGNORECASE)
        if match:
            try:
                parsed_date = date_parser.parse(match.group(1), fuzzy=True)
                if parsed_date:
                    return parsed_date.strftime("%Y-%m-%d")
            except:
                continue
    
    return None
```

#### **Enhanced Date Sanity Validation**
```python
def validate_date_sanity(date_iso: str) -> bool:
    """Enhanced date validation with stricter bounds and format checking."""
    try:
        # Must be valid ISO format
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_iso):
            return False
            
        year = int(date_iso[:4])
        month = int(date_iso[5:7])
        day = int(date_iso[8:10])
        
        current_year = datetime.now().year
        
        # Year bounds: 1900 to current + 2
        if not (1900 <= year <= (current_year + 2)):
            return False
            
        # Month bounds: 1-12
        if not (1 <= month <= 12):
            return False
            
        # Day bounds: 1-31 (basic check)
        if not (1 <= day <= 31):
            return False
            
        return True
    except (ValueError, IndexError):
        return False
```

---

## 🔧 **PHASE 2B: CORE IMPROVEMENTS (PRODUCTION HARDENING)**

### **4. Robust HTTP Client Behavior**

#### **Per-Host Concurrency Limiting**
- **Limit**: Maximum 2 concurrent requests per host
- **Implementation**: Use `asyncio.Semaphore` per host
- **Benefits**: Prevents overwhelming target sites, reduces 403/429 errors

#### **Exponential Backoff on 5xx Errors**
- **Strategy**: Retry with exponential backoff (1s, 2s, 4s, 8s)
- **Max Retries**: 3 attempts
- **Skip on**: 4xx errors (client errors, don't retry)

#### **Configurable Timeouts**
- **Environment Variable**: `HTTP_TIMEOUT_SECONDS` (default: 10)
- **Per-Request Timeout**: Respects configuration
- **Connection Timeout**: 5 seconds (hard limit)

#### **Rate Limiting**
- **Per-Host Rate**: Maximum 1 request per 2 seconds
- **Implementation**: `asyncio.Lock` with timestamp tracking
- **Benefits**: Respects web etiquette, reduces blocking

### **5. Enhanced Logging & Monitoring**

#### **Structured Candidate Logging**
```python
# DEBUG level for each candidate
logger.debug("Candidate parsed", extra={
    "host": candidate.source_host,
    "source_type": candidate.source_type,
    "date_iso": candidate.date_iso,
    "city": candidate.city,
    "venue": candidate.venue,
    "url": candidate.url
})
```

#### **Selection Decision Logging**
```python
# INFO level for selection decisions
logger.info("Selection completed", extra={
    "metro": metro,
    "decision_path": audit.decision_path,
    "candidates_considered": len(candidates),
    "best_source_type": best_candidate.source_type,
    "best_url": best_candidate.url,
    "selection_time_ms": selection_time
})
```

#### **Performance Metrics**
- **Response Time Tracking**: Per-endpoint timing
- **Success Rate Monitoring**: Track 2xx vs 4xx/5xx responses
- **Resource Usage**: Memory and CPU usage tracking

### **6. Comprehensive Testing Suite**

#### **Unit Tests**
- **Date Parsing Tests**: `test_parse_date_context_validation()`
- **HTTP Client Tests**: `test_concurrency_limiting()`, `test_backoff_strategy()`
- **Validation Tests**: `test_enhanced_date_sanity()`

#### **Integration Tests**
- **End-to-End Workflow**: Full artist → selection pipeline
- **Error Handling**: 403/429 → Wayback fallback scenarios
- **Performance Tests**: Concurrency and timeout validation

#### **Regression Tests**
- **All 8 Artists**: Ensure no regressions from Phase 1
- **Edge Cases**: Malformed dates, missing venues, etc.

---

## 🚀 **IMPLEMENTATION ORDER & TIMELINE**

### **Day 1: Date Parsing Fix (Priority 1)**
- [ ] **Morning**: Implement enhanced `parse_date()` function
- [ ] **Afternoon**: Test with Proxima Parada (ensure "1901 Union St" issue resolved)
- [ ] **Evening**: Validate all 8 artists (no regressions)

### **Day 2: HTTP Client Improvements (Priority 2)**
- [ ] **Morning**: Implement concurrency limiting and rate limiting
- [ ] **Afternoon**: Add exponential backoff and timeout handling
- [ ] **Evening**: Test HTTP client behavior with multiple concurrent requests

### **Day 3: Logging & Testing (Priority 3-4)**
- [ ] **Morning**: Implement structured logging and performance monitoring
- [ ] **Afternoon**: Create comprehensive test suite
- [ ] **Evening**: End-to-end validation and performance testing

---

## ✅ **SUCCESS CRITERIA**

### **Date Parsing Fix (Phase 2A)**
- [ ] **Proxima Parada Issue Resolved**: No more "1901-08-29" from "1901 Union St"
- [ ] **All 8 Artists Still Work**: No regressions in existing functionality
- [ ] **Date Sanity Validation**: Catches any remaining edge cases

### **HTTP Client Improvements (Phase 2B)**
- [ ] **Concurrency Limiting**: Maximum 2 concurrent requests per host
- [ ] **Rate Limiting**: 1 request per 2 seconds per host
- [ ] **Backoff Strategy**: Exponential retry on 5xx errors
- [ ] **Timeout Handling**: Configurable timeouts working correctly

### **Enhanced Logging (Phase 2B)**
- [ ] **Structured Logs**: JSON-formatted logs for operational monitoring
- [ ] **Selection Decisions**: Full audit trail for debugging
- [ ] **Performance Metrics**: Response times and success rates tracked

### **Testing Coverage (Phase 2B)**
- [ ] **Unit Tests**: 90%+ coverage for new functionality
- [ ] **Integration Tests**: End-to-end workflow validation
- [ ] **Regression Tests**: All existing functionality preserved

---

## 🔍 **RISK ASSESSMENT & MITIGATION**

### **High Risk: Date Parsing Changes**
- **Risk**: Could break existing working cases
- **Mitigation**: Comprehensive testing with all 8 artists before/after
- **Rollback Plan**: Feature flag to switch between old/new parsing

### **Medium Risk: HTTP Client Modifications**
- **Risk**: Could affect all external requests
- **Mitigation**: Implement gradually with feature flags
- **Monitoring**: Enhanced logging to catch issues early

### **Low Risk: Logging Changes**
- **Risk**: Could impact performance
- **Mitigation**: Use appropriate log levels, async logging where possible
- **Validation**: Performance testing before deployment

---

## 🧪 **TESTING STRATEGY**

### **Pre-Implementation Baseline**
- [x] **Completed**: All 8 artists tested and working
- [x] **Identified**: Proxima Parada date parsing issue
- [x] **Documented**: Current behavior and expected fixes

### **Implementation Validation**
- [ ] **Date Parsing Fix**: Test with Proxima Parada specifically
- [ ] **HTTP Client**: Test concurrency and rate limiting
- [ ] **Logging**: Verify structured logs are generated correctly

### **End-to-End Validation**
- [ ] **Full Workflow**: Artist → Songkick → Selection pipeline
- [ ] **Error Scenarios**: 403/429 → Wayback fallback
- [ ] **Performance**: Response times and resource usage

### **Regression Testing**
- [ ] **All 8 Artists**: Ensure no functionality lost
- [ ] **Edge Cases**: Malformed data, missing fields, etc.
- [ ] **Integration Points**: All endpoints working correctly

---

## 📊 **PERFORMANCE TARGETS**

### **Response Time**
- **Target**: < 2 seconds for single artist processing
- **Acceptable**: < 5 seconds under normal load
- **Monitoring**: Track 95th percentile response times

### **Success Rate**
- **Target**: > 95% successful responses
- **Acceptable**: > 90% under normal conditions
- **Monitoring**: Track 2xx vs 4xx/5xx response ratios

### **Resource Usage**
- **Memory**: < 512MB under normal load
- **CPU**: < 80% utilization during peak usage
- **Concurrency**: Support 10+ concurrent users

---

## 🚀 **DEPLOYMENT STRATEGY**

### **Phase 1: Date Parsing Fix (Day 1)**
- **Scope**: Critical bug fix only
- **Risk**: Low (isolated change)
- **Rollback**: Simple function reversion

### **Phase 2: HTTP Client (Day 2)**
- **Scope**: Infrastructure improvements
- **Risk**: Medium (affects all external requests)
- **Rollback**: Feature flag to disable new behavior

### **Phase 3: Logging & Testing (Day 3)**
- **Scope**: Observability and validation
- **Risk**: Low (additive changes)
- **Rollback**: Log level adjustments

---

## 📋 **CHECKLIST FOR COMPLETION**

### **Phase 2A: Date Parsing Fix**
- [ ] Enhanced `parse_date()` function implemented
- [ ] Proxima Parada issue resolved
- [ ] All 8 artists still working
- [ ] Date sanity validation enhanced

### **Phase 2B: HTTP Client Improvements**
- [ ] Concurrency limiting implemented
- [ ] Rate limiting implemented
- [ ] Exponential backoff working
- [ ] Timeout configuration working

### **Phase 2B: Enhanced Logging**
- [ ] Structured candidate logging
- [ ] Selection decision logging
- [ ] Performance metrics tracking
- [ ] Log levels configured correctly

### **Phase 2B: Testing & Validation**
- [ ] Unit tests created and passing
- [ ] Integration tests working
- [ ] End-to-end validation complete
- [ ] Performance targets met

---

## 🎯 **POST-PHASE 2 OUTCOME**

By the end of Phase 2, the Last-Show Oracle will have:

- **100% Date Parsing Accuracy**: No more malformed dates from street addresses
- **Production-Grade HTTP Client**: Resilient, rate-limited, and configurable
- **Comprehensive Operational Visibility**: Structured logging and performance monitoring
- **Robust Test Coverage**: Unit, integration, and regression tests
- **Maintained Backward Compatibility**: All existing functionality preserved

**The service will be ready for production deployment with confidence.**

---

## 📞 **NEXT STEPS**

1. **Review this plan** and provide feedback
2. **Approve implementation** to begin Phase 2A
3. **Monitor progress** through daily updates
4. **Validate results** with comprehensive testing
5. **Deploy to production** when all criteria met

---

**Document Version**: 1.0  
**Last Updated**: Current Session  
**Next Review**: After Phase 2A completion  
**Owner**: Development Team
