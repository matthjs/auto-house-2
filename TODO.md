# Doing

# Todo
- [ ] Use a model that parses images, and scrape the images of the places for the model as well.
- [ ] Get a scout to look at pages and get updates, pass that to a server
- [x] Parse the HTML better for the LLM (all sites: listing HTML is converted to text)
- [ ] Add Image to Email As attachment
- [x] Add link to the saved file for faster lookup (records store the listing URL; see `main.py status`)
- [x] Timestamp emails and messages saved (records have created/updated times and a history)
- [ ] Inbox agent: sort replies (viewing invite, rejection, question) and draft follow-ups for approval
- [ ] Replace fixed `time.sleep` waits in the scrapers with explicit Selenium waits
- [ ] Confirm a send succeeded on wgzimmer.ch (the button click sometimes misses silently)

# Not Urgent
- [ ] Test in WebInteractor that you have reached the given step for each function (using HTML headers?)
