/* Dashboard settings. Edit here, commit, done.

   SHARED_NOTES_URL: the Google Apps Script web app that the Maryland dashboard already
   uses (md-property-leads, docs/shared-notes-setup.md). Every status change and note is
   appended to that one Google Sheet and shown to everyone using either dashboard.
   Virginia rows are written with tab names that start "va-" and ids that start "va:",
   so the two tools never collide. Leave it empty and notes stay in each browser. */
window.VAPL = {
    SHARED_NOTES_URL: "https://script.google.com/macros/s/AKfycbzpEwPb5I4hEjA5YhtzfpcJSVRlhDJvQv5kAeV24KDJ9X9K5mA7QHkq1HJ-tYa_d2igUw/exec",
};
