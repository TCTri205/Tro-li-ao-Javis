-- Clear meeting transcript branch data before re-running load-data.
TRUNCATE TABLE public.chunks_turn, public.chunks_passage, public.transcripts CASCADE;
