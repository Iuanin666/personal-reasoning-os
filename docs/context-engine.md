# Context engine

Context Engine accepts a question, task type, subject, and optional `as_of`. It returns a bounded Context Pack with core context, personal evidence, external knowledge, source evidence, conflicts, missing information, and provenance.

`subject` distinguishes self, another person, and a general question. Historical questions respect event time and do not use current Profile to rewrite past reasons. Source evidence is loaded only when original wording, citations, or page verification is needed.
