OBJECTS := $(filter-out capi1.html,$(patsubst %.adoc,%.html,$(wildcard *.adoc)))

all: $(OBJECTS)

capi.html: capi1.adoc

capi1.adoc: ../fusesoc/capi1/section.py
	PYTHONPATH=.. python $< > $@

%.html: %.adoc
	asciidoc $<

clean:
	rm -f $(OBJECTS) capi1.adoc
