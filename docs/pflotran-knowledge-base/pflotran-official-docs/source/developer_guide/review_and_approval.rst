Back to :ref:`developer-guide`

.. _review_and_approval:

Review and Approval
===================
Review and approval for all modifications to the PFLOTRAN documentation, source code, or tests is as follows:
- All commits (modifications) uploaded to the main online repositories shall be automatically tested through cloud-based continuous integration resources.

- All pull requests submitted to the master branch shall be:

 + Reviewed by peers for consistency and conformance to coding and/or documentation standards,
 + Reviewed and approved by at least one Senior Developer.

- All pull requests submitted to the maintenance branches shall be:

 + Documented through a change request in Jira,
 + Reviewed by peers for consistency and conformance to coding and/or documentation standards,
 + Reviewed and approved by at least one Senior Developer.

Review and Approval for Software Releases
-----------------------------------------
PFLOTRAN documentation, source code, and tests are released 
periodically under a single version number as specified by the 
PFLOTRAN Configuration Management Plan.  Senior Developers ensure 
adherence to the configuration management plan and consistency 
among the three (documentation, source, tests).  Users are notified 
of the release through the user mailing list and an updated version 
number in the online documentation.  Users obtain the latest 
released software by cloning the main online repository and checking 
out the maintenance branch aligned with the release version number 
(provided in the installation instructions within the PFLOTRAN User 
Guide).
