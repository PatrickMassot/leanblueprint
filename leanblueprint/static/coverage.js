$(document).ready(function() {
    $("div.thm_thmheading").click(
           function() {
               $(this).siblings("div.thm_thm_content").slideToggle()
           })
    $("section h3").click(
           function() {
               $(this).siblings("ul.coverage").slideToggle()
           })
  });

