#!/usr/bin/env python

"""
Created on Apr 10, 2015

@author: Chen Yang

This script generates read profiles Oxford Nanopore 2D reads.

"""


from __future__ import print_function
from __future__ import with_statement
from subprocess import call
from time import strftime
try:
    from six.moves import xrange
except ImportError:
    pass
import sys
import os
import getopt
import argparse
import HTSeq
import numpy
from sklearn.neighbors import KernelDensity
from sklearn.externals import joblib
import head_align_tail_dist as align
import get_besthit_maf
import get_primary_sam
import besthit_to_histogram as error_model
import model_fitting
import model_intron_retention as model_ir


# Usage information
def usage():
    usage_message = "./read_analysis.py <options>\n" \
                    "<options>: \n" \
                    "-h : print usage message\n" \
                    "-i : training ONT real reads, must be fasta files\n" \
                    "-r : reference genome of the training reads\n" \
                    "-a : Aligner to be used: minimap2 or LAST, default = 'minimap2'\n" \
                    "-m : User can provide their own alignment file, with maf or sam extension, can be omitted\n" \
                    "-t : number of threads for alignment and model fitting, default = 1\n" \
                    "-o : The prefix of output file, default = 'training'\n" \
                    "--no_model_fit : Skip the model fitting step\n"

    sys.stderr.write(usage_message)

def align_transcriptome(g_alnm, t_alnm, prefix, aligner):

    if (g_alnm != '' and t_alnm == '') or (g_alnm == '' and t_alnm != ''):
        print("Please specify either both alignment files (-ga and -ta) OR an aligner to use for alignment (-a)")
        usage()
        sys.exit(1)
    if g_alnm != "" and t_alnm != "":
        g_alnm_filename, g_alnm_ext = os.path.splitext(g_alnm)
        t_alnm_filename, t_alnm_ext = os.path.splitext(t_alnm)
        g_alnm_ext = g_alnm_ext [1:]
        t_alnm_ext = t_alnm_ext[1:]
        if g_alnm_ext != t_alnm_ext:
            print("Please provide both alignments in a same format: sam OR maf\n")
            usage()
            sys.exit(1)
        else:
            sys.stdout.write(strftime("%Y-%m-%d %H:%M:%S") + ": Processing the alignment files: " + t_alnm_ext + "\n")
            if t_alnm_ext == "maf":
                outmaf_g = prefix + "_genome_alnm.maf"
                outmaf_t = prefix + "_transcriptome_alnm.maf"
                if outmaf_g == g_alnm:
                    outmaf_g = prefix + "_genome_alnm_processed.maf"
                if outmaf_t == t_alnm:
                    outmaf_t = prefix + "_transcriptome_alnm_processed.maf"

                call("grep '^s ' " + g_alnm + " > " + outmaf_g, shell=True)
                call("grep '^s ' " + t_alnm + " > " + outmaf_t, shell=True)

                unaligned_length = list(get_besthit_maf.besthit_and_unaligned(in_fasta, outmaf_t, prefix))

            elif t_alnm_ext == "sam":

                unaligned_length = list(get_primary_sam.primary_and_unaligned(g_alnm, t_alnm, prefix))

    elif (g_alnm == '' and t_alnm == ''):
        if aligner == "minimap2":
            g_alnm_ext = "sam"
            t_alnm_ext = "sam"
            outsam_g = prefix + "_genome_alnm.sam"
            outsam_t = prefix + "_transcriptome_alnm.sam"
            # Alignment to reference genome

            # [EDIT] I should change the options for minimap when dealing with cDNA and dRNA reads.
            sys.stdout.write(strftime("%Y-%m-%d %H:%M:%S") + ": Alignment with minimap2 to reference genome\n")
            call("minimap2 -ax splice " + ref_g + " " + in_fasta + " > " + outsam_g, shell=True)
            # Alignment to reference transcriptome
            sys.stdout.write(strftime("%Y-%m-%d %H:%M:%S") + ": Alignment with minimap2 to reference transcriptome\n")
            call("minimap2 --cs -ax map-ont " + ref_t + " " + in_fasta + " > " + outsam_t, shell=True)

            # [EDIT] I may add a script to remove minimap2/LAST post-alignment files after alignment.
            unaligned_length = list(get_primary_sam.primary_and_unaligned(outsam_g, outsam_t, prefix))

        elif aligner == "LAST":
            g_alnm_ext = "maf"
            t_alnm_ext = "maf"
            outmaf_g = prefix + "_genome_alnm.maf"
            outmaf_t = prefix + "_transcriptome_alnm.maf"
            # Alignment to reference genome
            sys.stdout.write(strftime("%Y-%m-%d %H:%M:%S") + ": Alignment with LAST to reference genome\n")
            call("lastdb ref_genome " + ref_g, shell=True)
            call("lastal -a 1 -P " + num_threads + " ref_genome " + in_fasta + " | grep '^s ' > " + outmaf_g,
                 shell=True)
            # Alignment to reference transcriptome
            sys.stdout.write(strftime("%Y-%m-%d %H:%M:%S") + ": Alignment with LAST to reference transcriptome\n")
            call("lastdb ref_transcriptome " + ref_t, shell=True)
            call("lastal -a 1 -P " + num_threads + " ref_transcriptome " + in_fasta + " | grep '^s ' > " + outmaf_t,
                 shell=True)

            unaligned_length = list(get_besthit_maf.besthit_and_unaligned(in_fasta, outmaf_t, prefix))

        else:
            print("Please specify an acceptable aligner (minimap2 or LAST)\n")
            usage()
            sys.exit(1)

    return t_alnm_ext, unaligned_length

def align_genome(g_alnm, prefix, aligner):
    # if an alignment file is provided
    if g_alnm != '':
        pre, file_ext = os.path.splitext(g_alnm)
        file_extension = file_ext[1:]
        sys.stdout.write(strftime("%Y-%m-%d %H:%M:%S") + ": Processing alignment file: " + file_extension + "\n")
        if file_extension == "maf":
            processed_maf = prefix + "_processed.maf"

            call("grep '^s ' " + alnm_file + " > " + processed_maf, shell=True)

            # get best hit and unaligned reads
            unaligned_length = get_besthit_maf.besthit_and_unaligned(in_fasta, processed_maf, prefix)

        elif file_extension == "sam":
            # get the primary alignments and define unaligned reads.
            unaligned_length = get_primary_sam.primary_and_unaligned(alnm_file, prefix)
        else:
            print("Please specify an acceptable alignment format! (.maf or .sam)\n")
            usage()
            sys.exit(1)

    # if alignment file is not provided
    else:
        if aligner == "minimap2" or aligner == "":  # Align with minimap2 by default
            file_extension = "sam"
            out_sam = prefix + ".sam"
            sys.stdout.write(strftime("%Y-%m-%d %H:%M:%S") + ": Alignment with minimap2\n")
            call("minimap2 --cs -ax map-ont -t " + num_threads + " " + ref + " " + in_fasta + " > " + out_sam,
                 shell=True)
            # get primary alignments and unaligned reads
            unaligned_length = get_primary_sam.primary_and_unaligned(out_sam, prefix)
        elif aligner == "LAST":
            file_extension = "maf"
            out_maf = prefix + ".maf"
            sys.stdout.write(strftime("%Y-%m-%d %H:%M:%S") + ": Alignment with LAST\n")
            call("lastdb ref_genome " + ref, shell=True)
            call("lastal -a 1 -P " + num_threads + " ref_genome " + in_fasta + " | grep '^s ' > " + out_maf, shell=True)
            unaligned_length = get_besthit_maf.besthit_and_unaligned(in_fasta, out_maf, prefix)
        else:
            print("Please specify an acceptable aligner (minimap2 or LAST)\n")
            usage()
            sys.exit(1)
    return file_extension, unaligned_length

def main(argv):
    # Parse input and output files

    prefix = 'training'
    model_fit = True
    intron_retention = True
    detect_IR = False
    quantify = False

    parser = argparse.ArgumentParser(
        description='Given the read profiles from characterization step, ' \
                    'simulate genomic/transcriptic ONT reads and output error profiles',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    subparsers = parser.add_subparsers(help = "You may run the simulator on transcriptome or genome mode. You may also only quanity expression profiles.", dest='mode')

    parser_g = subparsers.add_parser('genome', help="Run the simulator on genome mode.")
    parser_g.add_argument('-i', '--read', help='Input read for training.', required=False)
    parser_g.add_argument('-rg', '--ref_g', help='Reference genome.', required=False)
    parser_g.add_argument('-a', '--aligner', help='The aligner to be used minimap2 or LAST (Default = minimap2)', default = 'minimap2')
    parser_g.add_argument('-ga', '--g_alnm', help='Genome alignment file in sam or maf format (optional)', default= '')
    parser_g.add_argument('-o', '--output', help='The output name and location for profiles', default = "training")
    parser_g.add_argument('--no_model_fit', help='Disable model fitting step', action='store_true')
    parser_g.add_argument('-t', '--num_threads', help='Number of threads to be used in alignments and model fitting (Default = 1)', default=1)

    parser_t = subparsers.add_parser('transcriptome', help="Run the simulator on transcriptome mode.")
    parser_t.add_argument('-i', '--read', help='Input read for training.', required=False)
    parser_t.add_argument('-rg', '--ref_g', help='Reference genome.', required=False)
    parser_t.add_argument('-rt', '--ref_t', help='Reference Transcriptome.', required=False)
    parser_t.add_argument('-annot', '--annot', help='Annotation file in ensemble GTF/GFF formats.', required=False)
    parser_t.add_argument('-a', '--aligner', help='The aligner to be used minimap2 or LAST (Default = minimap2)', default = 'minimap2')
    parser_t.add_argument('-ga', '--g_alnm', help='Genome alignment file in sam or maf format (optional)', default= '')
    parser_t.add_argument('-ta', '--t_alnm', help='Transcriptome alignment file in sam or maf format (optional)', default= '')
    parser_t.add_argument('-o', '--output', help='The output name and location for profiles', default = "training")
    parser_t.add_argument('--no_model_fit', help='Disable model fitting step', action='store_true')
    parser_t.add_argument('--no_intron_retention', help='Disable Intron Retention analysis', action='store_true')
    parser_t.add_argument('--detect_IR', help='Detect Intron Retention events using input reads and exit', action='store_true')
    parser_t.add_argument('-b', '--num_bins', help='Number of bins to be used (Default = 20)', default = 20)
    parser_t.add_argument('-t', '--num_threads', help='Number of threads to be used in alignments and model fitting (Default = 1)', default=1)

    parser_e = subparsers.add_parser('quantify', help="Quantify expression profile of transcripts")
    parser_e.add_argument('-o', '--output', help='The output name and location', default="training")
    parser_e.add_argument('-i', '--read', help='Input reads to use to quantification.', required=True)
    parser_e.add_argument('-rt', '--ref_t', help='Reference Transcriptome.', required=True)
    parser_t.add_argument('-t', '--num_threads', help='Number of threads to be used (Default = 1)', default=1)

    parser_ir = subparsers.add_parser('detect_ir', help="Detect Intron Retention events using the input read")
    parser_ir.add_argument('-o', '--output', help='The output name and location for profiles', default = "training")


    args = parser.parse_args()
    #args_t = parser_t.parse_args()
    #args_g = parser_g.parse_args()
    #args_e = parser_e.parse_args()

    #parse transcriptome mode arguments.
    if args.mode == "transcriptome":
        infile = args.read
        ref_g = args.ref_g
        ref_t = args.ref_t
        annot = args.annot
        aligner = args.aligner
        g_alnm = args.g_alnm
        t_alnm = args.t_alnm
        prefix = args.output
        num_bins = max(args.num_bins, 20) #I may remove it because of ecdf > KDE
        num_threads = max(args.num_threads, 1)
        if args.no_model_fit:
            model_fit = False
        if args.no_intron_retention:
            intron_retention = False
        if args.detect_IR:
            detect_IR = True

    #parse genome mode arguments
    if args.mode == "genome":
        infile = args.read
        ref_g = args.ref_g
        aligner = args.aligner
        g_alnm = args.g_alnm
        prefix = args.output
        num_threads = max(args.num_threads, 1)
        if args.no_model_fit:
            model_fit = False

    #parse quanity mode arguments
    if args.mode == "quantify":
        infile = args.read
        ref_t = args.ref_t
        prefix = args.output
        num_threads = max(args.num_threads, 1)
        # Quantifying the transcript abundance from input read
        sys.stdout.write('Quantifying transcripts abundance: \n')
        call("minimap2 -t " + str(num_threads) + " -x map-ont -p0 " + ref_t + " " + infile + " > " + prefix + "_mapping.paf", shell=True)
        call("python nanopore_transcript_abundance.py -i " + prefix + "_mapping.paf > " + prefix + "_abundance.tsv",
             shell=True)
        sys.stdout.write('Finished! \n')
        sys.exit(1)

    if args.mode == "detect_ir":
        annot = args.annot
        prefix = args.output
        # Read the annotation GTF/GFF3 file
        sys.stdout.write(strftime("%Y-%m-%d %H:%M:%S") + ": Parse the annotation file (GTF/GFF3)\n")
        # If gtf provided, convert to GFF3 (gt gtf_to_gff3)
        annot_filename, annot_file_extension = os.path.splitext(annot)
        annot_file_extension = annot_file_extension[1:]
        if annot_file_extension.upper() == "GTF":
            call("gt gtf_to_gff3 -tidy -o " + prefix + ".gff3" + annot, shell=True)

        # Next, add intron info into gff3:
        call(
            "gt gff3 -tidy -retainids -checkids -addintrons -o " + prefix + "_addedintron.gff3 " + annot_filename + ".gff3",
            shell=True)

    # READ PRE-PROCESS AND ALIGNMENT ANALYSIS
    sys.stdout.write(strftime("%Y-%m-%d %H:%M:%S") + ": Read pre-process and unaligned reads analysis\n")
    # Read pre-process
    in_fasta = prefix + "_processed.fasta"  # use the prefix of input fasta file for processed fasta file
    processed_fasta = open(in_fasta, 'w')
    dic_reads = {}
    with open(infile, 'r') as f:
        for line in f:
            if line[0] == '>':
                name = '-'.join(line.strip()[1:].split())
                dic_reads[name] = ""
            else:
                dic_reads[name] += line.strip()
    for k, v in dic_reads.items():
        processed_fasta.write('>' + k + '\n' + v + '\n')
    processed_fasta.close()

    del dic_reads

    if args.mode == "genome":
        alnm_ext, unaligned_length = align_genome(g_alnm, prefix, aligner)

    if args.mode == "transcriptome":
        alnm_ext, unaligned_length = align_transcriptome(g_alnm, t_alnm, prefix, aligner)

        if detect_IR == "True":
            # Read the annotation GTF/GFF3 file
            sys.stdout.write(strftime("%Y-%m-%d %H:%M:%S") + ": Parse the annotation file (GTF/GFF3)\n")
            # If gtf provided, convert to GFF3 (gt gtf_to_gff3)
            annot_filename, annot_file_extension = os.path.splitext(annot)
            annot_file_extension = annot_file_extension[1:]
            if annot_file_extension.upper() == "GTF":
                call("gt gtf_to_gff3 -tidy -o " + prefix + ".gff3" + annot, shell=True)

            # Next, add intron info into gff3:
            call("gt gff3 -tidy -retainids -checkids -addintrons -o " + prefix + "_addedintron.gff3 " + annot_filename + ".gff3",
                shell=True)

        sys.stdout.write(strftime("%Y-%m-%d %H:%M:%S") + ": Read the length of reference transcripts \n")
        # Read the length of reference transcripts from the reference transcriptome
        dict_ref_len = {}
        with open(ref_t) as f:
            for line in f:
                if line.startswith(">"):
                    ref_id = line.split()[0][1:]
                    dict_ref_len[ref_id] = 0
                else:
                    dict_ref_len[ref_id] += len(line.strip())

        if intron_retention:
            # Read the annotation GTF/GFF3 file
            sys.stdout.write(strftime("%Y-%m-%d %H:%M:%S") + ": Parse the annotation file (GTF/GFF3)\n")
            # If gtf provided, convert to GFF3 (gt gtf_to_gff3)
            annot_filename, annot_file_extension = os.path.splitext(annot)
            annot_file_extension = annot_file_extension[1:]
            if annot_file_extension.upper() == "GTF":
                call("gt gtf_to_gff3 -tidy -o " + prefix + ".gff3" + annot, shell=True)

            # Next, add intron info into gff3:
            call("gt gff3 -tidy -retainids -checkids -addintrons -o " + prefix + "_addedintron.gff3 " + annot_filename + ".gff3",
                shell=True)
            sys.stdout.write(strftime("%Y-%m-%d %H:%M:%S") + ": Modeling Intron Retention\n")
            model_ir.intron_retention(prefix, ref_t)


    # Aligned reads analysis
    sys.stdout.write(strftime("%Y-%m-%d %H:%M:%S") + ": Aligned reads analysis\n")
    num_aligned = align.head_align_tail(prefix, alnm_ext)

    # Length distribution of unaligned reads
    alignment_rate = open(prefix + "_reads_alignment_rate", 'w')

    num_unaligned = len(unaligned_length)
    if num_unaligned != 0:
        alignment_rate.write("Aligned / Unaligned ratio:" + "\t" + str(num_aligned * 1.0 / num_unaligned) + '\n')
        unaligned_length_2d = unaligned_length[:, numpy.newaxis]
        kde_unaligned = KernelDensity(bandwidth=10).fit(unaligned_length_2d)
        joblib.dump(kde_unaligned, prefix + "_unaligned_length.pkl")
    else:
        alignment_rate.write("Aligned / Unaligned ratio:\t100%\n")

    alignment_rate.close()
    del unaligned_length

    # MATCH AND ERROR MODELS
    sys.stdout.write(strftime("%Y-%m-%d %H:%M:%S") + ": match and error models\n")
    error_model.hist(prefix, alnm_ext)

    if model_fit:
        sys.stdout.write(strftime("%Y-%m-%d %H:%M:%S") + ": Model fitting\n")
        model_fitting.model_fitting(prefix, int(num_threads))

    call("find . -name \*ref_genome.* -delete", shell=True)
    call("find . -name \*ref_transcriptome.* -delete", shell=True)
    call("find . -name \*.pyc -delete", shell=True)
    sys.stdout.write(strftime("%Y-%m-%d %H:%M:%S") + ": Finished!\n")


if __name__ == "__main__":
    main(sys.argv[1:])

