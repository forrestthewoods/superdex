// Stand-in for glibc's <sys/single_threaded.h> (glibc 2.32+). Zig ships the
// header for every glibc version but #errors below 2.32, and CGAL's
// config.h includes it whenever __has_include finds it. Our Linux target is
// glibc 2.28, so report "maybe multi-threaded", which is CGAL's own
// fallback when the header is missing.
#pragma once
// CGAL reads it as ::__libc_single_threaded, so it must be a variable.
static const char __libc_single_threaded = 0;
