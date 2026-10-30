# Software Requirements Specification — SecureDocs Portal

Version 2.0 (benchmark edition). This document is the source of srs_planted.docx; edit it here and rebuild with build_srs_planted.py.

## 1 Introduction

### 1.1 Purpose

This document specifies the requirements of SecureDocs, a web portal where employees of a company store, share and review confidential documents. It is written for the development team, the testers and the compliance office.

### 1.2 Scope

SecureDocs covers user accounts, sign-in, document storage, retention and notifications. Payroll, billing and the mobile apps are out of scope and are specified elsewhere.

### 1.3 Definitions

| Term | Meaning |
| Session | The time between a successful sign-in and sign-out or expiry. |
| Workspace administrator | An employee who manages the users of one workspace. |
| Recycle bin | The place where deleted documents wait before permanent removal. |

## 2 Overall Description

### 2.1 User Classes

Employees use SecureDocs every day to upload and read documents. Workspace administrators manage users and settings. Guests are external partners who receive shared documents. The compliance office reviews audit logs.

### 2.2 Operating Environment

SecureDocs runs in a private cloud and is used through current desktop browsers. All traffic uses TLS.

## 3 Specific Requirements

This section lists every requirement. Identifiers stay the same from one version to the next.

### 3.1 Authentication and Sessions

REQ-001: The system shall authenticate users with a username and password.
REQ-003: The system shall log every successful login attempt.
REQ-004: Admin sessions shall expire after 5 minutes of inactivity.
REQ-005: The system shall support multi-factor authentication.
REQ-009: The system shall support OAuth2 as an authentication provider.
REQ-010: The system shall record all failed login attempts.
REQ-014: Every unsuccessful login attempt shall be logged by the system.
REQ-016: The system shall support Google OAuth.
REQ-019: A second authentication factor shall be available at sign-in.
REQ-020: Guest sessions shall expire after 5 minutes of inactivity.
REQ-022: The system shall alert after five consecutive failed logins.
REQ-031: All successful login attempts shall be recorded by the system.
REQ-032: Sessions shall remain active until the user explicitly logs out.
REQ-036: The system shall allow at most 3 concurrent sessions per user.
REQ-037: A user shall be able to stay signed in on any number of devices at the same time.
REQ-040: The system shall lock an account after five consecutive failed login attempts.
REQ-041: After five failed sign-in attempts in a row, the user's account shall be locked by the system.
REQ-044: The system shall display the date and time of the user's last successful login after sign-in.
REQ-045: After signing in, users shall see when they last signed in successfully.
REQ-050: The system shall unlock a locked account when the user completes a password reset.
REQ-057: Passwords shall meet the password complexity policy.

Note: session limits apply to every browser tab of the same browser as one session.

### 3.2 Data Protection and Retention

REQ-002: The system shall store all user data encrypted at rest using AES-256.
REQ-012: User preference records shall be stored in a plaintext database.
REQ-013: Retention periods shall be configurable per data category.
REQ-017: User data shall be retained for the period configured for its data category.
REQ-024: Administrators shall be able to view each user's stored password in plaintext.
REQ-028: User passwords shall be hashed using bcrypt before storage.
REQ-034: Audit log entries shall be retained for seven years.
REQ-035: Audit log entries older than 12 months shall be deleted automatically.
REQ-038: Exported reports shall contain only anonymised data.
REQ-039: Each exported report shall list the full name and email address of every user it covers.
REQ-042: Users shall be able to download their own data in a machine-readable format.
REQ-043: The system shall let each user export the data held about them in a machine-readable format.
REQ-058: Security incident reports shall be retained for seven years.

### 3.3 Documents and Uploads

The following table lists the document requirements.

| ID | Requirement |
| REQ-011 | The system shall support multiple document formats. |
| REQ-025 | The system shall preserve the original requirement IDs from uploaded documents. |
| REQ-026 | The system shall reject files larger than 25 MB. |
| REQ-048 | Users shall be able to restore a deleted document within 30 days of deletion. |
| REQ-049 | Deleted documents shall be kept in a recycle bin for 30 days before permanent removal. |
| REQ-052 | The system shall handle a large number of simultaneous uploads. |
| REQ-056 | The system shall back up all documents. |
| REQ-059 | Guest users shall be able to download shared documents without signing in. |
| REQ-060 | The system shall time out file uploads after 10 minutes. |

### 3.4 Notifications and Reports

REQ-006: The system shall email a confirmation to the user after account creation.
REQ-008: The system shall store a verified email address for every user.
REQ-027: The system shall send a password reset email within 60 seconds of request.
REQ-030: The system shall notify the user when their account is modified.
REQ-046: The system shall send a monthly usage report to each workspace administrator by email.
REQ-047: The system shall store an email address for every workspace administrator.
REQ-055: Notifications shall be sent in a timely manner.

### 3.5 Performance, Availability and Usability

REQ-007: The system shall respond promptly to user input.
REQ-015: The user interface shall be user-friendly.
REQ-018: The system shall maintain 99.9% uptime.
REQ-021: API requests shall time out after 2 seconds.
REQ-023: API requests shall be permitted up to 10 seconds before timeout.
REQ-029: The system shall provide a modern look and feel.
REQ-033: The system shall time out database queries after 2 seconds.
REQ-051: Search results shall be displayed quickly.
REQ-053: Error messages shall be clear.
REQ-054: The system shall be highly secure.

## 4 Appendix

Requirements are numbered once and never reused. Gaps in the numbering are intentional.
