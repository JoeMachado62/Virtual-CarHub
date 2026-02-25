/*=== Javascript function indexing hear===========

1.counterUp ----------(Its use for counting number)
2.stickyHeader -------(header class sticky)
3.wowActive ----------( Waw js plugins activation)
4.swiperJs -----------(All swiper in this website hear)
5.salActive ----------(Sal animation for card and all text)
6.textChanger --------(Text flip for banner section)
7.timeLine -----------(History Time line)
8.datePicker ---------(On click date calender)
9.timePicker ---------(On click time picker)
10.timeLineStory -----(History page time line)
11.vedioActivation----(Vedio activation)
12.searchOption ------(search open)
13.cartBarshow -------(Cart sode bar)
14.sideMenu ----------(Open side menu for desktop)
15.Back to top -------(back to top)
16.filterPrice -------(Price filtering)

==================================================*/

(function ($) {
  'use strict';

  var rtsJs = {
    m: function (e) {
      rtsJs.d();
      rtsJs.methods();
    },
    d: function (e) {
      this._window = $(window),
        this._document = $(document),
        this._body = $('body'),
        this._html = $('html')
    },
    methods: function (e) {
      rtsJs.metismenu();
      rtsJs.swiperActive();
      rtsJs.wowActive();
      rtsJs.stickyHeader();
      rtsJs.backToTopInit();
      rtsJs.sideMenu();
      rtsJs.niceSelect();
      rtsJs.vedioActivation();
      rtsJs.videoActive();
      rtsJs.menuCurrentLink();
      rtsJs.preloader();
      rtsJs.counterUp();
      rtsJs.jarallax();
      rtsJs.stickyFooter();
      rtsJs.searchOption();
    },
    metismenu: function () {
      $('#mobile-menu-active').metisMenu();
    },
    swiperActive: function () {
      $(document).ready(function () {
        var swiper = new Swiper(".category-slider", {
          spaceBetween: 30,
          slidesPerView: 6,
          loop: true,
          speed: 1000,
          autoplay: {
            delay: 3000,
          },
          pagination: {
            el: ".swiper-pagination",
            clickable: true,
          },
          breakpoints: {
            1500: {
              slidesPerView: 6,
            },
            1440: {
              slidesPerView: 4,
            },
            991: {
              slidesPerView: 3,
            },
            767: {
              slidesPerView: 2,
            },
            575: {
              slidesPerView: 1,
            },
            0: {
              slidesPerView: 1,
            }
          },
        });
      });
      $(document).ready(function () {
        var swiper = new Swiper(".categorySlider2", {
          spaceBetween: 30,
          slidesPerView: 4,
          loop: true,
          speed: 1000,
          autoplay: {
            delay: 3000,
          },
          pagination: {
            el: ".swiper-pagination",
            clickable: true,
          },
          breakpoints: {
            1500: {
              slidesPerView: 4,
            },
            1199: {
              slidesPerView: 4,
            },
            991: {
              slidesPerView: 3,
            },
            767: {
              slidesPerView: 2,
            },
            575: {
              slidesPerView: 1,
            },
            0: {
              slidesPerView: 1,
            }
          },
        });
      });
      $(document).ready(function () {
        var swiper = new Swiper(".category-slider2", {
          spaceBetween: 25,
          slidesPerView: 6,
          loop: true,
          speed: 1000,
          autoplay: {
            delay: 3000,
          },
          pagination: {
            el: ".swiper-pagination-5",
            clickable: true,
          },
          breakpoints: {
            1500: {
              slidesPerView: 6,
            },
            1440: {
              slidesPerView: 5,
            },
            1200: {
              slidesPerView: 4,
            },
            991: {
              slidesPerView: 3,
            },
            767: {
              slidesPerView: 2,
            },
            575: {
              slidesPerView: 1,
            },
            0: {
              slidesPerView: 1,
            }
          },
        });
      });
      $(document).ready(function () {
        var swiper = new Swiper(".projectSlider", {
          spaceBetween: 50,
          slidesPerView: 2.2,
          centeredSlides: true,
          loop: true,
          speed: 1000,
          // autoplay: {
          //   delay: 3000,
          // },
          pagination: {
            el: ".swiper-pagination-2",
            clickable: true,
          },
          breakpoints: {
            1500: {
              slidesPerView: 2.2,
            },
            1199: {
              slidesPerView: 2,
            },
            991: {
              slidesPerView: 1,
            },
            767: {
              slidesPerView: 1,
            },
            575: {
              slidesPerView: 1,
            },
            0: {
              slidesPerView: 1,
            }
          },
        });
      });
      $(document).ready(function () {
        var swiper = new Swiper(".projectSlider2", {
          spaceBetween: 30,
          slidesPerView: 4,
          loop: true,
          speed: 1000,
          // autoplay: {
          //   delay: 3000,
          // },
          pagination: {
            el: ".swiper-pagination-2",
            clickable: true,
          },
          breakpoints: {
            1600: {
              slidesPerView: 4,
            },
            1440: {
              slidesPerView: 3,
            },
            1199: {
              slidesPerView: 3,
            },
            1100: {
              slidesPerView: 2,
            },
            800: {
              slidesPerView: 1,
            },
            575: {
              slidesPerView: 1,
            },
            320: {
              slidesPerView: 1,
            }
          },
        });
      });
      $(document).ready(function () {
        var swiper = new Swiper(".projectSlider3", {
          spaceBetween: 50,
          slidesPerView: 3,
          loop: true,
          centeredSlides: true,
          speed: 1000,
          // autoplay: {
          //   delay: 3000,
          // },
          pagination: {
            el: ".swiper-pagination-5",
            clickable: true,
          },
          breakpoints: {
            1500: {
              slidesPerView: 3,
            },
            1199: {
              slidesPerView: 3,
            },
            991: {
              slidesPerView: 2,
              centeredSlides: false,
            },
            767: {
              slidesPerView: 1,
            },
            575: {
              slidesPerView: 1,
            },
            0: {
              slidesPerView: 1,
            }
          },
        });
      });
      $(document).ready(function () {
        var swiper = new Swiper(".projectSlider4", {
          spaceBetween: 0,
          slidesPerView: 1,
          effect: "fade",
          loop: true,
          centeredSlides: true,
          speed: 1000,
          // autoplay: {
          //   delay: 3000,
          // },
          pagination: {
            el: ".swiper-pagination",
            clickable: true,
          },
        });
      });
      $(document).ready(function () {
        var swiper = new Swiper(".featureSlider", {
          spaceBetween: 30,
          slidesPerView: 1,
          loop: true,
          effect: "fade",
          speed: 1500,
          pagination: {
            el: ".swiper-pagination-3",
            clickable: true,
          },
        });
      });
      $(document).ready(function () {
        var swiper = new Swiper(".bannerSlider", {
          spaceBetween: 0,
          slidesPerView: 1,
          loop: true,
          effect: "fade",
          speed: 1500,
          navigation: {
            nextEl: ".swiper-button-next",
            prevEl: ".swiper-button-prev",
          },
        });
      });
      $(document).ready(function () {
        var swiper = new Swiper(".bannerSlider2", {
          spaceBetween: 0,
          slidesPerView: 1,
          loop: true,
          speed: 1500,
          navigation: {
            nextEl: ".swiper-button-next",
            prevEl: ".swiper-button-prev",
          },
        });
      });
      $(document).ready(function () {
        var swiper = new Swiper(".testimonialSlider", {
          spaceBetween: 30,
          slidesPerView: 1,
          // loop: true,
          speed: 1500,
          autoplay: {
            delay: 2000,
          },
          pagination: {
            el: ".swiper-pagination-4",
            clickable: true,
          },
        });
      });
      $(document).ready(function () {
        var swiper = new Swiper(".testimonialSlider2", {
          spaceBetween: 30,
          slidesPerView: 3,
          centeredSlides: true,
          loop: true,
          speed: 1000,
          // autoplay: {
          //   delay: 3000,
          // },
          pagination: {
            el: ".swiper-pagination-4",
            clickable: true,
          },
          breakpoints: {
            1500: {
              slidesPerView: 3,
            },
            1199: {
              centeredSlides: false,
              slidesPerView: 2,
            },
            991: {
              slidesPerView: 2,
            },
            767: {
              slidesPerView: 1,
            },
            575: {
              slidesPerView: 1,
            },
            0: {
              slidesPerView: 1,
            }
          },
        });
      });
      $(document).ready(function () {
        var swiper = new Swiper(".blogSlider", {
          spaceBetween: 30,
          slidesPerView: 3,
          loop: true,
          speed: 1000,
          // autoplay: {
          //   delay: 3000,
          // },
          pagination: {
            el: ".swiper-pagination-5",
            clickable: true,
          },
          breakpoints: {
            1500: {
              slidesPerView: 3,
            },
            1199: {
              slidesPerView: 2,
            },
            991: {
              slidesPerView: 2,
            },
            767: {
              slidesPerView: 1,
            },
            575: {
              slidesPerView: 1,
            },
            0: {
              slidesPerView: 1,
            }
          },
        });
      });
      $(document).ready(function () {
        // Check if the sliders exist on the page
        if ($(".rts-testimonialSlider3").length && $(".rts-imageSlider").length) {
          var swiper_1 = new Swiper(".rts-testimonialSlider3", {
            slidesPerView: 1,
            spaceBetween: 0,
            speed: 1800,
            loop: true,
            navigation: {
              nextEl: ".swiper-button-next",
              prevEl: ".swiper-button-prev",
            },
            modules: [Swiper.Controller], // Ensure Controller module is enabled
          });

          var swiper_2 = new Swiper(".rts-imageSlider", {
            slidesPerView: 1,
            spaceBetween: 0,
            effect: "fade",
            speed: 1800,
            loop: true,
            modules: [Swiper.Controller], // Ensure Controller module is enabled
          });

          // Synchronize the two Swipers
          swiper_1.controller.control = swiper_2;
          swiper_2.controller.control = swiper_1;
        }
      });
      $(document).ready(function () {
        var swiper6 = new Swiper('.rts-swiper-activation-6', {
          speed: 1000,
          spaceBetween: 30,
          slidesPerView: 3,
          loop: true,
          pagination: {
            el: '.swiper-pagination-5',
            clickable: true,
          },
          breakpoints: {
            1500: {
              slidesPerView: 3,
            },
            1199: {
              slidesPerView: 3,
            },
            991: {
              slidesPerView: 2,
            },
            767: {
              slidesPerView: 2,
            },
            575: {
              slidesPerView: 1,
            },
            0: {
              slidesPerView: 1,
            }
          },
          on: {
            slideChange: function () {
              let activeIndex = this.activeIndex;
              let slidesPerView = this.params.slidesPerView;

              // Convert this.slides to an array and remove the 'active-slide' class
              Array.from(this.slides).forEach(slide => {
                slide.classList.remove('active-slide');
              });

              // Loop through the visible slides and add the 'active-slide' class
              for (let i = 0; i < slidesPerView; i++) {
                let visibleSlideIndex = (activeIndex + i) % this.slides.length;
                this.slides[visibleSlideIndex].classList.add('active-slide');
              }
            }
          }
        });
      });
      $(document).ready(function () {
        // Check if the sliders exist on the page
        if ($(".rts-imgSliderBig").length && $(".rts-imgSliderSmall").length) {
          var swiper_1 = new Swiper(".rts-imgSliderBig", {
            slidesPerView: 1,
            effect: "fade",
            spaceBetween: 30,
            speed: 1800,
            loop: true,
            modules: [Swiper.Controller], // Ensure Controller module is enabled
          });

          var swiper_2 = new Swiper(".rts-imgSliderSmall", {
            slidesPerView: 2,
            spaceBetween: 30,
            speed: 1800,
            loop: true,
            pagination: {
              el: ".swiper-pagination",
              clickable: true,
            },
            breakpoints: {
              1500: {
                slidesPerView: 2,
              },
              1199: {
                slidesPerView: 2,
              },
              991: {
                slidesPerView: 2,
              },
              767: {
                slidesPerView: 1,
              },
              575: {
                slidesPerView: 1,
              },
              0: {
                slidesPerView: 1,
              }
            },
            modules: [Swiper.Controller], // Ensure Controller module is enabled
          });

          // Synchronize the two Swipers
          swiper_1.controller.control = swiper_2;
          swiper_2.controller.control = swiper_1;
        }
      });
    },
    jarallax: function (e) {
      $(document).ready(function () {
        // Function to detect if the device is mobile
        function isMobileDevice() {
          return /Android|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
        }

        // Initialize jarallax only if it's not a mobile device
        if (!isMobileDevice()) {
          $('.jarallax').jarallax();
        } else {
          console.log('Jarallax skipped on mobile devices');
        }
      });

    },
    wowActive: function () {
      new WOW().init();
    },
    stickyHeader: function (e) {
      $(window).scroll(function () {
        if ($(this).scrollTop() > 150) {
          $('.header--sticky').addClass('sticky')
        } else {
          $('.header--sticky').removeClass('sticky')
        }
      })
    },
    backToTopInit: function () {
      $(document).ready(function () {
        "use strict";

        var progressPath = document.querySelector('.progress-wrap path');
        var pathLength = progressPath.getTotalLength();
        progressPath.style.transition = progressPath.style.WebkitTransition = 'none';
        progressPath.style.strokeDasharray = pathLength + ' ' + pathLength;
        progressPath.style.strokeDashoffset = pathLength;
        progressPath.getBoundingClientRect();
        progressPath.style.transition = progressPath.style.WebkitTransition = 'stroke-dashoffset 10ms linear';
        var updateProgress = function () {
          var scroll = $(window).scrollTop();
          var height = $(document).height() - $(window).height();
          var progress = pathLength - (scroll * pathLength / height);
          progressPath.style.strokeDashoffset = progress;
        }
        updateProgress();
        $(window).scroll(updateProgress);
        var offset = 50;
        var duration = 550;
        jQuery(window).on('scroll', function () {
          if (jQuery(this).scrollTop() > offset) {
            jQuery('.progress-wrap').addClass('active-progress');
          } else {
            jQuery('.progress-wrap').removeClass('active-progress');
          }
        });
        jQuery('.progress-wrap').on('click', function (event) {
          event.preventDefault();
          jQuery('html, body').animate({ scrollTop: 0 }, duration);
          return false;
        })


      });
    },
    sideMenu: function () {

      // collups menu side right
      $(document).on('click', '#menu-btn', function () {
        $("#side-bar").addClass("show");
        $("#anywhere-home").addClass("bgshow");
      });
      $(document).on('click', '.close-icon-menu', function () {
        $("#side-bar").removeClass("show");
        $("#anywhere-home").removeClass("bgshow");
      });
      $(document).on('click', '#anywhere-home', function () {
        $("#side-bar").removeClass("show");
        $("#anywhere-home").removeClass("bgshow");
      });
      $(document).on('click', '.onepage .mainmenu li a', function () {
        $("#side-bar").removeClass("show");
        $("#anywhere-home").removeClass("bgshow");
      });
    },
    niceSelect: function () {
      (function ($) {
        $.fn.niceSelect = function (method) {
          if (typeof method === 'string') {
            return this.each(function () {
              var $select = $(this), $dropdown = $select.next('.nice-select');
              if (method === 'update') {
                if ($dropdown.length) $dropdown.remove();
                createNiceSelect($select);
              } else if (method === 'destroy') {
                if ($dropdown.length) $dropdown.remove();
                $select.show();
              }
            });
          }

          this.hide().each(function () {
            if (!$(this).next().hasClass('nice-select')) createNiceSelect($(this));
          });

          function createNiceSelect($select) {
            var $dropdown = $('<div class="nice-select" tabindex="0">' +
              '<span class="current"></span><ul class="list"></ul></div>');
            $select.after($dropdown);

            $select.find('option').each(function () {
              var $option = $(this);
              $('<li class="option" data-value="' + $option.val() + '">' +
                $option.text() + '</li>')
                .toggleClass('selected', $option.is(':selected'))
                .toggleClass('disabled', $option.is(':disabled'))
                .appendTo($dropdown.find('.list'));
            });

            $dropdown.find('.current').text($select.find('option:selected').text());
          }

          $(document).off('.nice_select')
            .on('click.nice_select', '.nice-select', function () {
              $('.nice-select').not(this).removeClass('open');
              $(this).toggleClass('open');
            })
            .on('click.nice_select', function (e) {
              if (!$(e.target).closest('.nice-select').length) $('.nice-select').removeClass('open');
            })
            .on('click.nice_select', '.nice-select .option:not(.disabled)', function () {
              var $option = $(this), $dropdown = $option.closest('.nice-select');
              $dropdown.find('.selected').removeClass('selected');
              $option.addClass('selected');
              $dropdown.find('.current').text($option.text());
              $dropdown.prev('select').val($option.data('value')).trigger('change');
            });

          return this;
        };

        $(document).ready(function () {
          $('select').niceSelect();
        });
      }(jQuery));
    },
    vedioActivation: function () {
      $(document).ready(function () {
        $('.popup-youtube, .popup-video').magnificPopup({
          type: 'iframe',
          mainClass: 'mfp-fade',
          removalDelay: 160,
          preloader: false,
          fixedContentPos: false
        });
      });
    },
    videoActive: function () {
      $(document).on('click', '#myBtn', function () {
        $("#myVideo").toggleClass("show");

        const $btn = $(this);
        const isFullSize = $btn.data("fullSize"); // Check if it's currently full size

        if (isFullSize) {
          $btn.css({
            opacity: "1",
            width: $btn.data("originalWidth"), // Restore original width
            height: $btn.data("originalHeight") // Restore original height
          }).data("fullSize", false);
        } else {
          // Store the original width and height before changing
          $btn.data("originalWidth", $btn.css("width"));
          $btn.data("originalHeight", $btn.css("height"));

          $btn.css({
            opacity: "0",
            width: "100%", // Set to 100% width
            height: "100%" // Set to 100% height
          }).data("fullSize", true);
        }
      });
      $(document).ready(function () {
        var $video = $("#myVideo");
        var $btn = $("#myBtn");

        if ($video.length && $btn.length) {
          $btn.on("click", function () {
            if ($video[0].paused) {
              $video[0].play();
            } else {
              $video[0].pause();
            }
          });
        }
      });

    },
    menuCurrentLink: function () {
      var currentPage = location.pathname.split("/"),
        current = currentPage[currentPage.length - 1];
      $('.parent-nav li > a').each(function () {
        var $this = $(this);
        if ($this.attr('href') === current) {
          $this.addClass('active');
          $this.parents('.has-dropdown').addClass('menu-item-open')
        }
      });
    },
    preloader: function () {
      window.addEventListener('load', function () {
        document.querySelector('body').classList.add("loaded")
      });
    },
    counterUp: function (e) {
      $('.counter').counterUp({
        delay: 10,
        time: 1000
      });
    },
    stickyFooter: function (e) {
      if (window.matchMedia('(min-width: 991px)').matches) {
        $(document).ready(function () {
          var footer_heights = $("#rts-footer").height();
          $(".rts-wrapper").css({
            'padding-bottom': footer_heights
          });
        });
        $(document).ready(function () {
          $(window).on("scroll", function () {
            var footer_height = $(".footer-sticky").outerHeight();
            var dim_height = $(".rts-footer-area").outerHeight();
            var scrollHeight = $(document).height();
            var scrollPosition = $(window).height() + $(window).scrollTop();
            if ((scrollHeight - scrollPosition) / scrollHeight === 0) {
              // when scroll to bottom of the page
              $(".rts-footer-area").removeClass("dim-fixed");
              $(".rts-footer-area").addClass("dim-static").css({
                'bottom': footer_height,
              });

            } else {
              $(".rts-footer-area").removeClass("dim-static");
              $(".rts-footer-area").addClass("dim-fixed").css({ 'bottom': 0, });
            }
          });
        }); //Document Ready function end
      }
    },
  
    // search popup
    searchOption: function () {
      $(document).on('click', '.search', function () {
        $(".search-input-area").addClass("show");
        $("#anywhere-home").addClass("bgshow");
      });
      $(document).on('click', '#close', function () {
        $(".search-input-area").removeClass("show");
        $("#anywhere-home").removeClass("bgshow");
      });
      $(document).on('click', '#anywhere-home', function () {
        $(".search-input-area").removeClass("show");
        $("#anywhere-home").removeClass("bgshow");
      });
    },
  }
  document.addEventListener("DOMContentLoaded", function () {
    var accordionHeaders = document.querySelectorAll(".accordion-header");
    accordionHeaders.forEach(function (header, index) {
      header.addEventListener("click", function () {
        var accordionItems = document.querySelectorAll(".accordion-item");
        accordionItems.forEach(function (item) {
          item.classList.remove("active");
        });
        var clickedItem = document.querySelectorAll(".accordion-item")[index];
        clickedItem.classList.add("active");
      });
    });
  });
  /* magnificPopup img view */
  $('.gallery-image').magnificPopup({
    type: 'image',
    gallery: {
      enabled: true
    }
  });
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
      e.preventDefault();

      const targetId = this.getAttribute('href');

      if (targetId === '#') {
        // If the link is the document header, scroll to the top of the page
        window.scrollTo({
          top: 0,
          behavior: 'smooth'
        });
      } else {
        // Get the target element
        const targetElement = document.querySelector(targetId);

        if (targetElement) {
          // Calculate the position 50px above the target element
          const targetPosition = targetElement.getBoundingClientRect().top + window.scrollY - 80;

          // Scroll to the calculated position
          window.scrollTo({
            top: targetPosition,
            behavior: 'smooth'
          });
        }
      }
    });
  });
  rtsJs.m();

})(jQuery, window)







